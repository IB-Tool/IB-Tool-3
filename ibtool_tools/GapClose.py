# -*- coding: utf-8 -*-
"""Gap closing tool for settlement polygon layers.

Provides two complementary gap-closing strategies:

1. **Block-based** (Process 1): detects gaps inside street blocks via
   symmetrical difference with the block layer, then filters candidates by
   area and boundary-overlap share.
2. **Buffer-based** (Process 2): uses a double-buffer morphological closing
   to bridge narrow inter-cluster gaps.

Public API
----------
gap_close(input_layer, blocks, max_hole_size, max_gap_size, crs,
          gap_dist, debug_mode, workspace_path)
gap_close_in_holes(input_layer, buffer_dist,
                   debug_mode, workspace_path)
"""
from qgis.core import QgsVectorLayer, QgsProcessing

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run


# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "06_GapClose"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Topology correction
TOPOLOGY_SNAP_BUFFER_M = 0.1
"""Tiny positive buffer (m) to snap sub-millimetre topology gaps in results."""

TOPOLOGY_SNAP_BUFFER_HOLES_M = 0.4
"""Snap buffer (m) used during morphological closing of hole polygons."""

TOPOLOGY_GRID_SIZE = 0.00001
"""Grid size for symmetrical difference and difference operations."""

# Boundary overlap analysis
SEGMENT_LENGTH_M = 10
"""Split length (m) for gap boundary segments used in overlap measurement."""

BOUNDARY_SNAP_BUFFER_M = 0.5
"""Buffer distance (m) around settlement boundary lines to catch near-touches."""

EDGE_ZONE_BUFFER_MARGIN_M = 0.3
"""Extra margin (m) added to gap_dist for the negative-buffer edge zone."""

# Gap selection thresholds
BOUNDARY_OVERLAP_THRESHOLD_PCT = 70
"""Standard minimum share (%) of a gap boundary that must touch the settlement."""

BOUNDARY_OVERLAP_STRICT_PCT = 90
"""Strict minimum share (%) for large gaps that are almost fully enclosed."""

MIN_GAP_AREA_SCALE_FACTOR = 200
"""Base area (m²) for the artefact filter; scaled by ``gap_dist / 15``."""

# Hole analysis
HOLE_DETECTION_THRESHOLD_M2 = 1_000_000
"""Area threshold (m²) — fills all realistic holes to expose hole polygons (1 km²)."""

MIN_PROCESSED_HOLE_AREA_M2 = 500
"""Minimum area (m²) a morphologically closed hole candidate must have to be kept."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _dissolve_union(input_layer, debug_mode=False, workspace_path=None):
    """Dissolves all features into a single geometry using a safe union workaround.

    Applies ``fix → collect → buffer(0, dissolve=True)`` instead of
    ``native:dissolve`` to avoid the GEOS bug that silently produces empty
    or null geometry on large MultiPolygon datasets.

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        debug_mode: If True, debug files may be saved on processing errors.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer with all features dissolved into one geometry.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': input_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    collected = safe_processing_run("native:collect", {
        'INPUT': fixed,
        'FIELD': [],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    dissolved = safe_processing_run("native:buffer", {
        'INPUT': collected,
        'DISTANCE': 0,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    return dissolved


def _gap_select(input_poly, input_gaps, crs, length_percentage):
    """Selects gaps based on the share of their boundary overlapping with the input polygon.

    The algorithm measures how much of each gap polygon's perimeter runs along
    the settlement boundary. Only gaps whose overlapping share exceeds
    ``length_percentage`` are returned, filtering out candidates that are
    merely adjacent to or outside the settlement.

    Args:
        input_poly: Input polygon layer (QgsVectorLayer).
        input_gaps: Gap polygon layer (QgsVectorLayer).
        crs: Coordinate reference system (accepted for API compatibility,
            currently unused inside this function).
        length_percentage: Minimum percentage of a gap's boundary that must
            overlap with the input polygon boundary for the gap to be selected.

    Returns:
        QgsVectorLayer containing the selected gap polygons.
    """
    # Dissolve input polygon to a single geometry for boundary comparison
    input_poly_diss = safe_processing_run("qgis:dissolve", {
        'INPUT': input_poly,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Convert settlement polygon and gap polygons to boundary lines
    input_poly_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': input_poly_diss,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    gap_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': input_gaps,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Explode multipart gap lines to singlepart for per-feature length measurement
    gap_lines_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': gap_lines,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Record total boundary length of each gap line (length_1) before splitting
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

    # Copy the feature ID to a persistent field so it survives the dissolve step
    gap_lines_with_fid_copy = safe_processing_run("native:fieldcalculator", {
        'INPUT': gap_lines_with_length,
        'FIELD_NAME': 'fid_copy',
        'FIELD_TYPE': 0,
        'FIELD_LENGTH': 0,
        'FIELD_PRECISION': 0,
        'FORMULA': '@id',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Split gap boundary lines into short segments for fine-grained overlap measurement
    split_lines = safe_processing_run("native:splitlinesbylength", {
        'INPUT': gap_lines_with_fid_copy,
        'LENGTH': SEGMENT_LENGTH_M,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Buffer settlement boundary lines to catch nearly-touching gap segments
    input_poly_lines_buff = safe_processing_run("native:buffer", {
        'INPUT': input_poly_lines,
        'DISTANCE': BOUNDARY_SNAP_BUFFER_M,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Keep only gap segments that intersect the settlement boundary buffer
    overlapping_segments = safe_processing_run("native:extractbylocation", {
        'INPUT': split_lines,
        'PREDICATE': [0],  # intersect
        'INTERSECT': input_poly_lines_buff,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Dissolve matched segments by source gap ID to sum up the overlapping length (length_2)
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

    # Keep gaps where the overlapping share (length_2 / length_1) exceeds the threshold
    final_selection = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': lines_with_length_2,
        'EXPRESSION': f'("length_2" / "length_1") * 100 > {length_percentage}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'KEEP_FIELDS': True
    })['OUTPUT']

    # Collect the source gap IDs that passed the overlap filter
    fid_copy_values = [
        feature['fid_copy']
        for feature in final_selection.getFeatures()
    ]

    Logger.log(
        f"GapClose/gap_select(threshold={length_percentage}%): "
        f"input_gaps={input_gaps.featureCount()}, "
        f"overlapping_segments={overlapping_segments.featureCount()}, "
        f"ratio_passed={final_selection.featureCount()}, "
        f"matched_fids={len(fid_copy_values)}",
        level="INFO"
    )

    if not fid_copy_values:
        Logger.log(
            f"GapClose/gap_select(threshold={length_percentage}%): "
            f"no gaps passed the boundary-overlap filter → returning empty layer",
            level="INFO"
        )
        # Return an empty layer with the same schema as input_gaps
        empty_layer = QgsVectorLayer("Polygon", "empty", "memory")
        empty_layer.setCrs(input_gaps.crs())
        provider = empty_layer.dataProvider()
        provider.addAttributes(input_gaps.fields())
        empty_layer.updateFields()
        return empty_layer

    # Select the original gap polygons by spatial relation to the passing lines
    filtered_features = safe_processing_run("native:extractbylocation", {
        'INPUT': input_gaps,
        'PREDICATE': [0, 4],
        'INTERSECT': final_selection,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    return filtered_features


def _close_block_gaps(input_diss, blocks, max_hole_size, max_gap_size, crs, _dbg):
    """Closes small gaps inside street blocks (Process 1).

    Computes the symmetrical difference between the street block layer and the
    dissolved settlement polygon. Small fragments (area < ``max_gap_size``)
    whose boundary overlaps at least ``BOUNDARY_OVERLAP_THRESHOLD_PCT`` % with
    the settlement are merged back into it. Also closes gaps within large
    interior holes via ``gap_close_in_holes``.

    Args:
        input_diss: Dissolved settlement polygon layer (QgsVectorLayer).
        blocks: Street block polygon layer (QgsVectorLayer).
        max_hole_size: Area threshold in m² for interior hole filling.
        max_gap_size: Area threshold in m² — only fragments smaller than
            this are treated as gaps.
        crs: Coordinate reference system of the layers.
        _dbg: Debug parameter dict forwarded to safe_processing_run calls
            (keys: ``debug_mode``, ``workspace_path``, ``tool_name``).

    Returns:
        QgsVectorLayer with block-based and hole-interior gaps closed.
    """
    debug_mode = _dbg.get('debug_mode', False)
    workspace_path = _dbg.get('workspace_path', None)

    # Fill interior holes before sym-diff to prevent confusing them with gaps
    hole_closed = safe_processing_run("native:deleteholes", {
        'INPUT': input_diss,
        'MIN_AREA': max_hole_size,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(hole_closed, _DEBUG_TOOL_NAME, "01_hole_closed", workspace_path)

    # Fix geometries on both inputs to prevent sym-diff failures
    blocks_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': blocks,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    hole_closed_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': hole_closed,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Symmetrical difference: result contains block areas XOR settlement areas;
    # settlement-only areas are removed later by _gap_select based on boundary overlap
    block_sym_diff = safe_processing_run("qgis:symmetricaldifference", {
        'INPUT': blocks_fixed,
        'OVERLAY': hole_closed_fixed,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(block_sym_diff, _DEBUG_TOOL_NAME, "03_block_sym_diff", workspace_path)

    # Explode multipart polygons so each gap fragment is a separate feature
    block_sym_diff_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': block_sym_diff,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Keep only small fragments — these are the candidate gap areas inside blocks
    selected_areas = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': block_sym_diff_single,
        'EXPRESSION': f"area($geometry) < {max_gap_size}",
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(selected_areas, _DEBUG_TOOL_NAME, "04_selected_areas", workspace_path)

    # Confirm that candidate gaps share >= BOUNDARY_OVERLAP_THRESHOLD_PCT of their
    # boundary with the settlement — filters out block fragments that are not actual gaps
    merged_gap = _gap_select(hole_closed, selected_areas, crs, BOUNDARY_OVERLAP_THRESHOLD_PCT)
    if debug_mode and workspace_path:
        save_debug_layer(merged_gap, _DEBUG_TOOL_NAME, "05_merged_gap", workspace_path)

    # Absorb confirmed gap polygons into the settlement polygon and dissolve
    merged_output = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [merged_gap, hole_closed],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    dissolved_output = safe_processing_run("native:dissolve", {
        'INPUT': merged_output,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(dissolved_output, _DEBUG_TOOL_NAME, "06_dissolved_output", workspace_path)

    # Close gaps embedded inside large interior holes (missed by both other approaches)
    dissolved_output = gap_close_in_holes(
        dissolved_output,
        debug_mode=debug_mode, workspace_path=workspace_path
    )
    if debug_mode and workspace_path:
        save_debug_layer(dissolved_output, _DEBUG_TOOL_NAME, "07_hole_gaps_closed", workspace_path)

    # Final hole removal to clean up any remaining small interior rings
    holes_closed = safe_processing_run("native:deleteholes", {
        'INPUT': dissolved_output,
        'MIN_AREA': max_hole_size,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    Logger.log(
        f"GapClose – holes_closed: {holes_closed.featureCount()} features after "
        f"deleteholes (min_area={max_hole_size})",
        level="INFO"
    )

    return holes_closed


def _close_buffer_gaps(holes_closed, input_layer, max_hole_size, max_gap_size,
                       gap_dist, crs, _dbg):
    """Closes inter-cluster gaps using a double-buffer approach (Process 2).

    Expands the settlement by ``gap_dist`` (merging clusters whose separation
    is < 2 × ``gap_dist``), extracts the outer boundary ring, removes it via a
    second buffer, and subtracts the original buildings. The remaining interior
    area represents the inter-cluster gaps, which are then filtered by area and
    boundary-overlap share before being merged back into the settlement.

    Args:
        holes_closed: Settlement layer with holes and block gaps already closed
            (QgsVectorLayer).
        input_layer: Original input polygon layer (QgsVectorLayer), used to
            subtract building footprints from gap candidates.
        max_hole_size: Area threshold in m² for the final interior hole removal.
        max_gap_size: Area threshold in m² — only gaps below this are closed.
        gap_dist: Expansion distance in metres for the outer buffer.
        crs: Coordinate reference system of the layers.
        _dbg: Debug parameter dict forwarded to safe_processing_run calls
            (keys: ``debug_mode``, ``workspace_path``, ``tool_name``).

    Returns:
        QgsVectorLayer with inter-cluster gaps closed and a snap buffer applied.
    """
    debug_mode = _dbg.get('debug_mode', False)
    workspace_path = _dbg.get('workspace_path', None)

    # Expand the settlement by gap_dist with DISSOLVE=True so that clusters
    # whose separation < 2×gap_dist merge, turning the gap into interior area
    initial_buffer = safe_processing_run("native:buffer", {
        'INPUT': holes_closed,
        'DISTANCE': gap_dist,
        'DISSOLVE': True,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(initial_buffer, _DEBUG_TOOL_NAME, "08_initial_buffer", workspace_path)

    # Extract the outer boundary of the expanded polygon as lines
    boundary_line = safe_processing_run("native:polygonstolines", {
        'INPUT': initial_buffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Buffer the outer boundary to create an edge zone covering the full outer ring
    boundary_buffer = safe_processing_run("native:buffer", {
        'INPUT': boundary_line,
        'DISTANCE': gap_dist + EDGE_ZONE_BUFFER_MARGIN_M,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Remove the outer ring → remaining interior area contains the inter-cluster gaps
    poly_cut_1 = safe_processing_run("native:difference", {
        'INPUT': initial_buffer,
        'OVERLAY': boundary_buffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(poly_cut_1, _DEBUG_TOOL_NAME, "10_poly_cut_inner_ring", workspace_path)

    # Subtract original buildings so gap candidates contain only empty space
    poly_cut_2 = safe_processing_run("native:difference", {
        'INPUT': poly_cut_1,
        'OVERLAY': input_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(poly_cut_2, _DEBUG_TOOL_NAME, "11_poly_cut_minus_buildings", workspace_path)

    # Small positive buffer to close sub-metre topology gaps in the candidates
    poly_cut_2_puffer = safe_processing_run("native:buffer", {
        'INPUT': poly_cut_2,
        'DISTANCE': EDGE_ZONE_BUFFER_MARGIN_M,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Explode multipart result so each gap candidate is a separate feature
    poly_singlepart = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': poly_cut_2_puffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Filter 1: Remove tiny artefacts — minimum area scales linearly with gap_dist
    min_gap_area = MIN_GAP_AREA_SCALE_FACTOR * gap_dist / 15
    small_removed = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': poly_singlepart,
        'EXPRESSION': f'area($geometry) > {min_gap_area}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(small_removed, _DEBUG_TOOL_NAME, "12_small_removed", workspace_path)

    # Filter 2: >= BOUNDARY_OVERLAP_THRESHOLD_PCT of boundary touching settlement.
    # Uses holes_closed (1 dissolved feature) instead of input_layer (N buildings):
    # qgis:dissolve silently fails on large building datasets (same GEOS bug as
    # native:dissolve), producing empty dissolve → overlapping_segments=0 for all gaps.
    # holes_closed is geometrically correct: inter-cluster gap edges lie on its perimeter.
    final_gap1 = _gap_select(holes_closed, small_removed, crs, BOUNDARY_OVERLAP_THRESHOLD_PCT)
    if debug_mode and workspace_path:
        save_debug_layer(final_gap1, _DEBUG_TOOL_NAME, "13.1_final_gap1_70pct", workspace_path)
    Logger.log(f"GapClose – final_gap1 (70%): {final_gap1.featureCount()} features", level="INFO")

    # Filter 3: Strict variant — >= BOUNDARY_OVERLAP_STRICT_PCT for large enclosed gaps
    final_gap2 = _gap_select(holes_closed, small_removed, crs, BOUNDARY_OVERLAP_STRICT_PCT)
    if debug_mode and workspace_path:
        save_debug_layer(final_gap2, _DEBUG_TOOL_NAME, "13.2_final_gap2_90pct", workspace_path)
    Logger.log(f"GapClose – final_gap2 (90%): {final_gap2.featureCount()} features", level="INFO")

    # Filter 2b: From the 70%-selection, keep only polygons smaller than max_gap_size
    gap_poly_max_size = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': final_gap1,
        'EXPRESSION': f'area($geometry) < {max_gap_size}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(gap_poly_max_size, _DEBUG_TOOL_NAME, "14_gap_poly_max_size", workspace_path)
    Logger.log(
        f"GapClose – gap_poly_max_size: {gap_poly_max_size.featureCount()} features "
        f"after area filter (< {max_gap_size} m²)",
        level="INFO"
    )

    # Merge size-filtered gaps, large enclosed gaps, and settlement; dissolve to absorb all
    Logger.log(
        f"GapClose – merge input counts: "
        f"gap_poly_max_size={gap_poly_max_size.featureCount()}, "
        f"final_gap2={final_gap2.featureCount()}, "
        f"holes_closed={holes_closed.featureCount()}",
        level="INFO"
    )
    merged_final = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [gap_poly_max_size, final_gap2, holes_closed],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # Remove duplicate geometries that can arise from overlapping gap polygons
    repaired_output = safe_processing_run("qgis:deleteduplicategeometries", {
        'INPUT': merged_final,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    dissolved_final = safe_processing_run("native:dissolve", {
        'INPUT': repaired_output,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Final hole removal to fill any remaining interior rings smaller than max_hole_size
    dissolved_final_hole_closed = safe_processing_run("native:deleteholes", {
        'INPUT': dissolved_final,
        'MIN_AREA': max_hole_size,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(dissolved_final_hole_closed, _DEBUG_TOOL_NAME, "15_result", workspace_path)

    # Tiny positive buffer to snap any sub-millimetre topology gaps in the result
    final_buffer = safe_processing_run("native:buffer", {
        'INPUT': dissolved_final_hole_closed,
        'DISTANCE': TOPOLOGY_SNAP_BUFFER_M,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    return final_buffer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    # Fix geometries and dissolve all features into one (safe workaround for GEOS bug)
    input_diss = _dissolve_union(input_layer, debug_mode=debug_mode, workspace_path=workspace_path)

    if input_diss.featureCount() == 0:
        return input_layer

    # Process 1: Block-based gap close + gap close within interior holes
    holes_closed = _close_block_gaps(input_diss, blocks, max_hole_size, max_gap_size, crs, _dbg)

    # Process 2: Buffer-based inter-cluster gap close
    return _close_buffer_gaps(
        holes_closed, input_layer, max_hole_size, max_gap_size, gap_dist, crs, _dbg
    )


def gap_close_in_holes(input_layer, buffer_dist=15,
                       debug_mode=False, workspace_path=None):
    """Closes gaps within holes using morphological closing (double buffer).

    Identifies all holes in the input polygon by removing them with a large
    threshold (``HOLE_DETECTION_THRESHOLD_M2``) and subtracting the original
    geometry. Applies a positive then negative buffer of ``buffer_dist`` to
    the hole polygons to close narrow gaps within them. Qualifying holes are
    merged back into the settlement polygon.

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        buffer_dist: Buffer distance for the double-buffer in metres (default: 15).
        debug_mode: If True, intermediate layers are saved as debug files.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer with qualifying holes filled.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    # Small snap buffer to close sub-metre topology gaps before further processing
    input_buffered = safe_processing_run("native:buffer", {
        'INPUT': input_layer,
        'DISTANCE': TOPOLOGY_SNAP_BUFFER_M,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Fix and dissolve the buffered input (safe workaround for GEOS dissolve bug)
    input_diss = _dissolve_union(input_buffered, debug_mode=debug_mode, workspace_path=workspace_path)

    if input_diss.featureCount() == 0:
        return input_layer

    # --- Step 1: Identify holes ---
    # Remove all holes up to HOLE_DETECTION_THRESHOLD_M2 → yields settlement without rings
    filled = safe_processing_run("native:deleteholes", {
        'INPUT': input_diss,
        'MIN_AREA': HOLE_DETECTION_THRESHOLD_M2,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Subtract original polygon → remaining area equals the hole polygons
    holes = safe_processing_run("native:difference", {
        'INPUT': filled,
        'OVERLAY': input_diss,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes, _DEBUG_TOOL_NAME, "07.1_holes_identified", workspace_path)

    if holes.featureCount() == 0:
        return input_layer

    # Explode multipart hole result to singlepart for individual processing
    holes_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': holes,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # --- Step 2: Double buffer on holes (morphological closing) ---
    # Convert hole polygons to boundary lines so the buffer expands outward from
    # the hole perimeter rather than filling the interior
    holes_single_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': holes_single,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Positive buffer: expands the hole boundary by buffer_dist, merging nearby
    # holes into one shape and bridging narrow internal gaps
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

    # Convert expanded polygon to boundary lines for the negative buffer step
    holes_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': holes_expanded,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Buffer boundary lines inward to create an edge zone covering the outer ring
    holes_line_buffer = safe_processing_run("native:buffer", {
        'INPUT': holes_lines,
        'DISTANCE': buffer_dist + EDGE_ZONE_BUFFER_MARGIN_M,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Subtract the edge zone to restore the approximate original hole shape with
    # internal gaps now closed
    holes_shrunk = safe_processing_run("native:difference", {
        'INPUT': holes_expanded,
        'OVERLAY': holes_line_buffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes_shrunk, _DEBUG_TOOL_NAME, "07.3_holes_shrunk", workspace_path)

    # Tiny positive buffer to close sub-metre topology gaps before splitting to singlepart
    holes_shrunk_puffer = safe_processing_run("native:buffer", {
        'INPUT': holes_shrunk,
        'DISTANCE': TOPOLOGY_SNAP_BUFFER_HOLES_M,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # Explode multipart result to singlepart for per-hole area filtering
    holes_shrunk_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': holes_shrunk_puffer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    # --- Step 3: Filter holes by minimum area ---
    # Only keep processed hole areas larger than MIN_PROCESSED_HOLE_AREA_M2
    # to avoid filling tiny artefacts from the morphological closing
    holes_to_close = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': holes_shrunk_single,
        'EXPRESSION': f'area($geometry) > {MIN_PROCESSED_HOLE_AREA_M2}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(holes_to_close, _DEBUG_TOOL_NAME, "07.4_holes_to_close", workspace_path)

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
        save_debug_layer(result, _DEBUG_TOOL_NAME, "07.5_result", workspace_path)

    return result
