from qgis.core import QgsVectorLayer, QgsProcessing
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer

def safe_processing_run(algorithm_name, parameters, fix_geometries=True,
                        debug_mode=False, workspace_path=None, tool_name="GapClose"):
    """Safe wrapper for processing.run with automatic geometry repair on failure.

    Args:
        algorithm_name: Name of the QGIS processing algorithm to run.
        parameters: Parameter dictionary for the algorithm.
        fix_geometries: If True, attempts to repair invalid geometries and
            retries the algorithm before raising an error.
        debug_mode: If True, saves failing input layers as debug files.
        workspace_path: Base path for debug output files.
        tool_name: Tool name used as the debug sub-folder prefix.

    Returns:
        Result dictionary returned by processing.run.

    Raises:
        Exception: Re-raises the original exception if the error is not
            geometry-related or if all repair attempts fail.
    """
    try:
        return processing.run(algorithm_name, parameters)
    except Exception as e:
        error_msg = str(e).lower()
        geometry_error_hints = [
            'ungültige geometrie', 'invalid geometry',
            'objekt nicht schreiben', 'could not write',
            'self-intersection', 'self intersection',
        ]
        is_geometry_error = any(hint in error_msg for hint in geometry_error_hints)

        # Debug: Fehlerhafte Input-Layer speichern
        if debug_mode and workspace_path:
            for key, value in parameters.items():
                if key in ['INPUT', 'OVERLAY', 'INTERSECT'] and hasattr(value, 'isValid'):
                    step = f"{algorithm_name.replace(':', '_')}_{key}"
                    save_debug_layer(value, tool_name, step, workspace_path, is_error=True)

        if fix_geometries and is_geometry_error:
            Logger.log(f"Geometry error in {algorithm_name}, attempting repair: {e}", level="WARNING")
            # Versuche alle Input-Layer zu reparieren
            repaired_params = parameters.copy()
            for key, value in parameters.items():
                if key in ['INPUT', 'OVERLAY', 'INTERSECT'] and hasattr(value, 'isValid'):
                    try:
                        repaired_layer = processing.run("native:fixgeometries", {
                            'INPUT': value,
                            'METHOD': 1,
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']
                        repaired_params[key] = repaired_layer
                    except:
                        pass  # Falls Reparatur fehlschlägt, ursprünglichen Layer verwenden

            # Erneut versuchen mit reparierten Geometrien
            try:
                return processing.run(algorithm_name, repaired_params)
            except Exception as e2:
                Logger.log(f"Retry after repair failed for {algorithm_name}: {e2}", level="WARNING")
                # Letzter Versuch: Ungültige Geometrien ignorieren
                if 'INVALID_FEATURE_HANDLING' not in repaired_params:
                    repaired_params['INVALID_FEATURE_HANDLING'] = 1
                return processing.run(algorithm_name, repaired_params)
        else:
            Logger.log(str(e), level="CRITICAL")
            raise e


def gap_close(input_layer, blocks, max_hole_size, max_gap_size, crs, gap_dist=15,
              debug_mode=False, workspace_path=None):
    """Closes gaps within and between settlement polygons.

    Uses two complementary methods: block-based gap detection (symmetrical
    difference with street blocks) and buffer-based gap detection (double
    buffer to bridge narrow inter-cluster gaps).

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        blocks: Street block polygon layer (QgsVectorLayer).
        max_hole_size: Area threshold in m² — interior holes smaller than
            this value are filled.
        max_gap_size: Area threshold in m² — gaps smaller than this value
            are closed.
        crs: Coordinate reference system of the layers.
        gap_dist: Buffer distance in metres for double-buffer gap detection
            (default: 15).
        debug_mode: If True, intermediate layers are saved as debug files.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer containing the settlement polygons with gaps closed.
    """
    # Debug-Parameter für safe_processing_run vorbereiten
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name="GapClose")

    def gap_select(input_poly, input_gaps, crs, length_percentage):
        """Selects gaps based on the share of their boundary overlapping with the input polygon.

        Args:
            input_poly: Input polygon layer (QgsVectorLayer).
            input_gaps: Gap polygon layer (QgsVectorLayer).
            crs: Coordinate reference system (accepted for API compatibility,
                currently unused).
            length_percentage: Minimum percentage of a gap's boundary that must
                overlap with the input polygon boundary for the gap to be selected.

        Returns:
            QgsVectorLayer containing the selected gap polygons.
        """

        # Input Polygon auflösen
        input_poly_diss = safe_processing_run("qgis:dissolve", {
            'INPUT': input_poly,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Polygone in Linien umwandeln
        input_poly_lines = safe_processing_run("native:polygonstolines", {
            'INPUT': input_poly_diss,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        gap_lines = safe_processing_run("native:polygonstolines", {
            'INPUT': input_gaps,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Multipart zu Singlepart für Lückenlinien
        gap_lines_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': gap_lines,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Felder hinzufügen und Längen berechnen
        gap_lines_with_length = safe_processing_run("qgis:fieldcalculator", {
            'INPUT': gap_lines_single,
            'FIELD_NAME': 'length_1',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 20,
            'FIELD_PRECISION': 10,
            'NEW_FIELD': True,
            'FORMULA': '$length',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        gap_lines_with_fid_copy = safe_processing_run("native:fieldcalculator", {
            'INPUT': gap_lines_with_length,
            'FIELD_NAME': 'fid_copy',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 0,
            'FIELD_PRECISION': 0,
            'FORMULA': '@id',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Linien an Schnittpunkten teilen
        split_lines = safe_processing_run("native:splitlinesbylength", {
            'INPUT': gap_lines_with_fid_copy,
            'LENGTH': 10,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        input_poly_lines_buff = safe_processing_run("native:buffer", {
            'INPUT': input_poly_lines,
            'DISTANCE': 0.5,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': False,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Überlappende Segmente extrahieren
        overlapping_segments = safe_processing_run("native:extractbylocation", {
            'INPUT': split_lines,
            'PREDICATE': [0],  # intersect
            'INTERSECT': input_poly_lines_buff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Segmente nach FID auflösen und neue Länge berechnen
        dissolved_segments = safe_processing_run("qgis:dissolve", {
            'INPUT': overlapping_segments,
            'FIELD': ['fid_copy'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_with_length_2 = safe_processing_run("qgis:fieldcalculator", {
            'INPUT': dissolved_segments,
            'FIELD_NAME': 'length_2',
            'FIELD_TYPE': 0,
            'FIELD_LENGTH': 20,
            'FIELD_PRECISION': 10,
            'NEW_FIELD': True,
            'FORMULA': '$length',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Längenverhältnis berechnen und filtern
        final_selection = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': lines_with_length_2,
            'EXPRESSION': f'("length_2" / "length_1") * 100 > {length_percentage}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'KEEP_FIELDS': True
        })['OUTPUT']

        # Retrieve all values from the 'fid_copy' field in final_selection and store them in a list
        fid_copy_values = [
            feature['fid_copy']
            for feature in final_selection.getFeatures()
        ]

        Logger.log(
            f"GapClose/gap_select(threshold={length_percentage}%): "
            f"input_gaps={input_gaps.featureCount()}, "
            f"overlapping_segments={overlapping_segments.featureCount()}, "
            f"ratio_passed={final_selection.featureCount()}, "
            f"matched_fids={len(fid_copy_values)}"
        )

        if not fid_copy_values:
            Logger.log(
                f"GapClose/gap_select(threshold={length_percentage}%): "
                f"no gaps passed the boundary-overlap filter → returning empty layer",
                level="WARNING"
            )
            # Erstelle leeres Polygon mit gleicher Struktur wie input_gaps
            empty_layer = QgsVectorLayer("Polygon", "empty", "memory")
            empty_layer.setCrs(input_gaps.crs())

            # Kopiere Felder vom input_gaps
            provider = empty_layer.dataProvider()
            provider.addAttributes(input_gaps.fields())
            empty_layer.updateFields()

            return empty_layer

        # Ansonsten normale Filterung durchführen
        filtered_features = safe_processing_run("native:extractbylocation", {
            'INPUT': input_gaps,
            'PREDICATE': [0, 4],
            'INTERSECT': final_selection,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        return filtered_features

    ############################################################

    # Fix geometries, then dissolve via collect + buffer(0) workaround
    # native:dissolve silently fails on large MultiPolygon sets (GEOS bug)
    input_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': input_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Collect all features into one multipart geometry
    input_collected = safe_processing_run("native:collect", {
        'INPUT': input_fixed,
        'FIELD': [],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Buffer(0) forces a proper geometric union via GEOS
    input_diss = safe_processing_run("native:buffer", {
        'INPUT': input_collected,
        'DISTANCE': 0,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    input_layer_count = input_diss.featureCount()

    if input_layer_count > 0:
        # ── Prozess 1: Block-basierter Gap Close ─────────────────────────────
        # Identifiziert kleine Lücken innerhalb von Straßenblöcken via
        # symmetrischer Differenz (Blocks XOR Siedlung).

        # Close holes in the input polygons
        hole_closed = safe_processing_run("native:deleteholes", {
            'INPUT': input_diss,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(hole_closed, "GapClose", "01_hole_closed", workspace_path)

        # Fix geometries on both inputs before symmetrical difference
        blocks_fixed = safe_processing_run("native:fixgeometries", {
            'INPUT': blocks,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(blocks_fixed, "GapClose", "02_blocks_fixed", workspace_path)

        hole_closed_fixed = safe_processing_run("native:fixgeometries", {
            'INPUT': hole_closed,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Symmetrical difference between blocks and hole-closed polygons
        block_sym_diff = safe_processing_run("qgis:symmetricaldifference", {
            'INPUT': blocks_fixed,
            'OVERLAY': hole_closed_fixed,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': 0.00001
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(block_sym_diff, "GapClose", "03_block_sym_diff", workspace_path)

        # Convert multipart polygons to singlepart
        block_sym_diff_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': block_sym_diff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Filter areas smaller than max_gap_size
        selected_areas = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': block_sym_diff_single,
            'EXPRESSION': f"area($geometry) < {max_gap_size}",
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(selected_areas, "GapClose", "04_selected_areas", workspace_path)

        # Merge selected gaps with hole_closed polygons
        merged_gap = gap_select(hole_closed, selected_areas, crs, 70)
        if debug_mode and workspace_path:
            save_debug_layer(merged_gap, "GapClose", "05_merged_gap", workspace_path)

        merged_output = safe_processing_run("native:mergevectorlayers", {
            'LAYERS': [merged_gap, hole_closed],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_output = safe_processing_run("native:dissolve", {
            'INPUT': merged_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(dissolved_output, "GapClose", "06_dissolved_output", workspace_path)

        # ── Prozess 1.5: Lücken in Löchern schließen ─────────────────────────
        dissolved_output = gap_close_in_holes(
            dissolved_output, max_hole_size,
            debug_mode=debug_mode, workspace_path=workspace_path
        )
        if debug_mode and workspace_path:
            save_debug_layer(dissolved_output, "GapClose", "07_hole_gaps_closed", workspace_path)

        holes_closed = safe_processing_run("native:deleteholes", {
            'INPUT': dissolved_output,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(holes_closed, "GapClose", "07b_holes_closed", workspace_path)
        Logger.log(f"GapClose – holes_closed: {holes_closed.featureCount()} features after deleteholes (min_area={max_hole_size})")

        # ── Prozess 2: Puffer-basierter Gap Close ────────────────────────────
        # Identifiziert Lücken zwischen Siedlungsclustern via Doppelpufferung.

        # DISSOLVE=True is essential: merges all cluster buffers into one polygon so that
        # the gap area between clusters becomes part of the interior (not near the outer
        # boundary). Without dissolve, each cluster's boundary_buffer removes its own
        # 15m buffer ring → the inter-cluster gap never reaches poly_cut_1.
        initial_buffer = safe_processing_run("native:buffer", {
            'INPUT': holes_closed,
            'DISTANCE': gap_dist,
            'DISSOLVE': True,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(initial_buffer, "GapClose", "08_initial_buffer", workspace_path)

        boundary_line = safe_processing_run("native:polygonstolines", {
            'INPUT': initial_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        boundary_buffer = safe_processing_run("native:buffer", {
            'INPUT': boundary_line,
            'DISTANCE': gap_dist + 0.3,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(boundary_buffer, "GapClose", "09_boundary_buffer", workspace_path)

        poly_cut_1 = safe_processing_run("native:difference", {
            'INPUT': initial_buffer,
            'OVERLAY': boundary_buffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': 0.00001,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(poly_cut_1, "GapClose", "10_poly_cut_inner_ring", workspace_path)

        poly_cut_2 = safe_processing_run("native:difference", {
            'INPUT': poly_cut_1,
            'OVERLAY': input_layer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': 0.00001,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(poly_cut_2, "GapClose", "11_poly_cut_minus_buildings", workspace_path)

        poly_cut_2_puffer = safe_processing_run("native:buffer", {
            'INPUT': poly_cut_2,
            'DISTANCE': 0.3,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']


        poly_singlepart = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': poly_cut_2_puffer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Critter 1: Remove small polygons based on area relative to gap distance
        small_removed = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': poly_singlepart,
            'EXPRESSION': f'area($geometry) > {200 * gap_dist / 15}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(small_removed, "GapClose", "12_small_removed", workspace_path)

        # Critter 2: Select gaps whose boundary overlaps the settlement by at least 70%.
        # Uses holes_closed (1 dissolved feature) instead of input_layer (N buildings):
        # qgis:dissolve silently fails on large building datasets (same GEOS bug as
        # native:dissolve), producing an empty dissolve result → input_poly_lines_buff
        # becomes empty → overlapping_segments=0 for every gap polygon.
        # holes_closed is geometrically correct here: inter-cluster gap edges lie on
        # the outer settlement boundary, which is exactly holes_closed's perimeter.
        final_gap1 = gap_select(holes_closed, small_removed, crs, 70)
        if debug_mode and workspace_path:
            save_debug_layer(final_gap1, "GapClose", "13.1_final_gap1_70pct", workspace_path)
        Logger.log(f"GapClose – final_gap1 (70%): {final_gap1.featureCount()} features")

        # Critter 3: Stricter gap selection — boundary overlap at least 90%
        final_gap2 = gap_select(holes_closed, small_removed, crs, 90)
        if debug_mode and workspace_path:
            save_debug_layer(final_gap2, "GapClose", "13.2_final_gap2_90pct", workspace_path)
        Logger.log(f"GapClose – final_gap2 (90%): {final_gap2.featureCount()} features")

        # Critter 2b: From the 70%-selection, keep only polygons smaller than max_gap_size
        gap_poly_max_size = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': final_gap1,
            'EXPRESSION': f'area($geometry) < {max_gap_size}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(gap_poly_max_size, "GapClose", "14_gap_poly_max_size", workspace_path)
        Logger.log(f"GapClose – gap_poly_max_size: {gap_poly_max_size.featureCount()} features after area filter (< {max_gap_size} m²)")

        Logger.log(
            f"GapClose – merge input counts: "
            f"gap_poly_max_size={gap_poly_max_size.featureCount()}, "
            f"final_gap2={final_gap2.featureCount()}, "
            f"holes_closed={holes_closed.featureCount()}"
        )
        merged_final = safe_processing_run("native:mergevectorlayers", {
            'LAYERS': [gap_poly_max_size, final_gap2, holes_closed],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        repaired_output = safe_processing_run("qgis:deleteduplicategeometries", {
            'INPUT': merged_final,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        dissolved_final = safe_processing_run("native:dissolve", {
            'INPUT': repaired_output,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }, **_dbg)['OUTPUT']

        # Close holes in the input polygons
        dissolved_final_hole_closed = safe_processing_run("native:deleteholes", {
            'INPUT': dissolved_final,
            'MIN_AREA': max_hole_size,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(dissolved_final_hole_closed, "GapClose", "15_result", workspace_path)

        final_buffer = safe_processing_run("native:buffer", {
            'INPUT': dissolved_final_hole_closed,
            'DISTANCE': 0.1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        return final_buffer
    else:
        return input_layer


def gap_close_in_holes(input_layer, max_hole_size, buffer_dist=15,
                       debug_mode=False, workspace_path=None):
    """Closes gaps within holes using morphological closing (double buffer).

    Identifies all holes in the input polygon by removing them with a large
    threshold (1 km²) and subtracting the original geometry. Applies a
    positive then negative buffer of ``buffer_dist`` to the hole polygons to
    close narrow gaps within them. Qualifying holes are merged back into the
    settlement polygon.

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        max_hole_size: Area threshold in m² — intended to filter holes that
            should be closed. Currently accepted for API compatibility but not
            yet applied inside this function (see hardcoded filter in Step 3).
        buffer_dist: Buffer distance for the double-buffer in metres (default: 15).
        debug_mode: If True, intermediate layers are saved as debug files.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer with qualifying holes filled.
    """
    # Threshold large enough to remove all realistic holes when identifying them
    HOLE_DETECTION_THRESHOLD = 1_000_000  # 1 km²

    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name="GapClose")

    # Small buffer to close sub-metre topology gaps before further processing
    input_buffered = safe_processing_run("native:buffer", {
        'INPUT': input_layer,
        'DISTANCE': 0.1,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Fix and dissolve input (collect + buffer(0) avoids GEOS bug in native:dissolve)
    input_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': input_buffered,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    input_collected = safe_processing_run("native:collect", {
        'INPUT': input_fixed,
        'FIELD': [],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    input_diss = safe_processing_run("native:buffer", {
        'INPUT': input_collected,
        'DISTANCE': 0,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    if input_diss.featureCount() == 0:
        return input_layer

    # --- Step 1: Identify holes ---
    # Remove all holes up to 1 km² → yields the settlement without any interior rings
    filled = safe_processing_run("native:deleteholes", {
        'INPUT': input_diss,
        'MIN_AREA': HOLE_DETECTION_THRESHOLD,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Subtract the original polygon → the remaining area equals the hole polygons
    holes = safe_processing_run("native:difference", {
        'INPUT': filled,
        'OVERLAY': input_diss,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': 0.00001,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes, "GapClose", "07.1_holes_identified", workspace_path)

    if holes.featureCount() == 0:
        return input_layer

    holes_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': holes,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # --- Step 2: Double buffer on holes (morphological closing) ---
    # Positive buffer: merges holes that are close together, fills narrow gaps within them

    # Convert expanded hole polygons to boundary lines
    holes_single_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': holes_single,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    holes_expanded = safe_processing_run("native:buffer", {
        'INPUT': holes_single_lines,
        'DISTANCE': buffer_dist,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes_expanded, "GapClose", "07.2_holes_expanded", workspace_path)

    # Convert expanded hole polygons to boundary lines
    holes_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': holes_expanded,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Buffer the boundary lines to create an edge zone (band around the perimeter)
    holes_line_buffer = safe_processing_run("native:buffer", {
        'INPUT': holes_lines,
        'DISTANCE': buffer_dist + 0.3,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Subtract the edge zone from the expanded holes to restore approximate original shape
    holes_shrunk = safe_processing_run("native:difference", {
        'INPUT': holes_expanded,
        'OVERLAY': holes_line_buffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': 0.00001,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes_shrunk, "GapClose", "07.3_holes_shrunk", workspace_path)

    holes_shrunk_puffer = safe_processing_run("native:buffer", {
        'INPUT': holes_shrunk,
        'DISTANCE': 0.4,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']


    holes_shrunk_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': holes_shrunk_puffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # --- Step 3: Select holes whose processed area is below the threshold ---
    holes_to_close = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': holes_shrunk_single,
        'EXPRESSION': f'area($geometry) > 500',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes_to_close, "GapClose", "07.4_holes_to_close", workspace_path)

    if holes_to_close.featureCount() == 0:
        return input_layer

    # --- Step 4: Fill selected holes by merging them into the settlement polygon ---
    merged = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [input_diss, holes_to_close],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    result = safe_processing_run("native:dissolve", {
        'INPUT': merged,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(result, "GapClose", "07.5_result", workspace_path)

    return result