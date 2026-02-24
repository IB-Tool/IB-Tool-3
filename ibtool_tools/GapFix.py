from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsSpatialIndex,
    QgsProcessing,
)

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run


def gap_fix(Inputpoly, InputRoadnetwork=None, workspace_path=None,
            bufferwidth=70, max_gap=10.0, debug_mode=False):
    """
    Closes narrow gaps between adjacent polygon features and removes interior
    holes (inner rings) from input polygons.

    Algorithm:
      1. Fix geometries
      2. Close holes: polygons → lines → polygonize → dissolve (fills inner rings)
      3. Multipart → singlepart, assign unique integer field ``gap_uid``
      4. Build buffer rings: buffer each polygon by max_gap, subtract all originals
         → donut-shaped ring per polygon that covers only empty space
      5. Pairwise intersect all buffer rings using a spatial index.
         Intersection areas = gap zones between two polygons.
      6. Validate each gap zone: keep only those that intersect both source polygons
         (filters out exterior buffer fringes and artefacts)
      7. Merge each valid gap zone into the adjacent polygon with the longer
         shared boundary
      8. Return updated layer

    Note on attributes: the global dissolve in step 2 rebuilds polygon topology,
    so original feature attributes are replaced by the new ``gap_uid`` field.

    Note on native:dissolve: intentionally avoided — it silently fails on large
    MultiPolygon datasets. The workaround native:collect + native:buffer(0,
    dissolve=True) is used throughout.

    Requires QGIS >= 3.20. Input layer must use a metric CRS (units = meters).

    :param Inputpoly: Input polygon layer (QgsVectorLayer or path string).
    :param InputRoadnetwork: Not used; kept for API compatibility.
    :param workspace_path: Workspace path for debug output.
    :param bufferwidth: Not used; kept for API compatibility.
    :param max_gap: Buffer distance and effective maximum gap width to close (m).
    :param debug_mode: If True, saves intermediate layers for debugging.
    :return: QgsVectorLayer with interior holes removed and gaps filled.
    """
    Logger.log("GapFix Start", level="INFO")
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name="GapFix")
    input_layer = None

    try:
        # --- Input resolution ---
        if isinstance(Inputpoly, str):
            input_layer = QgsVectorLayer(Inputpoly, "input", "ogr")
        else:
            input_layer = Inputpoly

        if not input_layer.isValid() or input_layer.featureCount() == 0:
            Logger.log("GapFix: No valid input geometries, returning unchanged.", level="INFO")
            return input_layer

        # --- Step 0: Fix geometries ---
        fixed = safe_processing_run("native:fixgeometries", {
            'INPUT': input_layer,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(fixed, "GapFix", "step0_fixed", workspace_path)

        # --- Step 1: Close interior holes ---
        # polygons → lines → polygonize → collect + buffer(0, dissolve=True)
        # Polygonize creates faces for all enclosed rings (including hole areas).
        # Dissolving everything merges hole faces into the surrounding polygon area.
        Logger.log("GapFix: Step 1 – closing interior holes…", level="INFO")

        lines = safe_processing_run("native:polygonstolines", {
            'INPUT': fixed,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        faces = safe_processing_run("native:polygonize", {
            'INPUT': lines,
            'KEEP_FIELDS': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        collected_faces = safe_processing_run("native:collect", {
            'INPUT': faces,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        dissolved = safe_processing_run("native:buffer", {
            'INPUT': collected_faces,
            'DISTANCE': 0,
            'DISSOLVE': True,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        if debug_mode and workspace_path:
            save_debug_layer(dissolved, "GapFix", "step1_dissolved", workspace_path)

        # --- Step 2: Multipart → singlepart + unique ID field ---
        Logger.log("GapFix: Step 2 – singleparts and unique IDs…", level="INFO")

        singleparts = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': dissolved,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        clean_polys = safe_processing_run("native:addautoincrementalfield", {
            'INPUT': singleparts,
            'FIELD_NAME': 'gap_uid',
            'START': 1,
            'MODULUS': 0,
            'GROUP_FIELDS': [],
            'SORT_EXPRESSION': '',
            'SORT_ASCENDING': True,
            'SORT_NULLS_FIRST': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        if debug_mode and workspace_path:
            save_debug_layer(clean_polys, "GapFix", "step2_clean_polys", workspace_path)

        Logger.log(f"GapFix: {clean_polys.featureCount()} polygon(s) after step 2.", level="INFO")

        # --- Step 3: Buffer rings (buffer minus all originals = donut per polygon) ---
        Logger.log(f"GapFix: Step 3 – building buffer rings (distance={max_gap})…", level="INFO")

        buffered_polys = safe_processing_run("native:buffer", {
            'INPUT': clean_polys,
            'DISTANCE': max_gap,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 2,
            'MITER_LIMIT': 2,
            'DISSOLVE': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        # Subtract ALL original polygons from ALL buffer polygons.
        # This ensures buffer rings contain only empty space, not polygon-occupied area.
        buffer_rings = safe_processing_run("native:difference", {
            'INPUT': buffered_polys,
            'OVERLAY': clean_polys,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': 0.00001,
        }, **_dbg)['OUTPUT']

        if debug_mode and workspace_path:
            save_debug_layer(buffer_rings, "GapFix", "step3_buffer_rings", workspace_path)

        # --- Step 4: Pairwise intersect buffer rings → gap zone candidates ---
        # ring_i ∩ ring_j = area in the buffer zone of both i and j, in no polygon
        #                  = the gap between polygon i and polygon j
        Logger.log("GapFix: Step 4 – pairwise buffer ring intersections…", level="INFO")

        ring_feats = {}
        ring_idx = QgsSpatialIndex()
        for f in buffer_rings.getFeatures():
            g = f.geometry()
            if g and not g.isEmpty():
                ring_feats[f.id()] = (f['gap_uid'], g)
                ring_idx.addFeature(f)

        gap_zones = []  # list of (gap_geom, uid_a, uid_b)
        for fid_a, (uid_a, geom_a) in ring_feats.items():
            for fid_b in ring_idx.intersects(geom_a.boundingBox()):
                if fid_b <= fid_a:
                    continue  # skip self and already-processed pairs (i < j only)
                uid_b, geom_b = ring_feats[fid_b]
                if uid_a == uid_b:
                    continue  # same source polygon (safety check)
                intersection = geom_a.intersection(geom_b)
                if intersection and not intersection.isEmpty() and intersection.area() > 0:
                    gap_zones.append((intersection, uid_a, uid_b))

        Logger.log(f"GapFix: {len(gap_zones)} gap zone candidate(s) found.", level="INFO")

        # --- Step 5: Keep only gap zones that intersect both source polygons ---
        # Exterior buffer fringes touch only 1 polygon → discarded.
        # Artefacts from distant polygon pairs don't touch either → discarded.
        Logger.log("GapFix: Step 5 – validating gap zones…", level="INFO")

        uid_to_geom = {}
        uid_to_feat = {}
        fid_to_uid = {}
        orig_idx = QgsSpatialIndex()
        for f in clean_polys.getFeatures():
            g = f.geometry()
            if g and not g.isEmpty():
                uid = f['gap_uid']
                uid_to_geom[uid] = g
                uid_to_feat[uid] = f
                fid_to_uid[f.id()] = uid
                orig_idx.addFeature(f)

        valid_gaps = []
        for gap_geom, uid_a, uid_b in gap_zones:
            candidates = orig_idx.intersects(gap_geom.boundingBox())
            touching_uids = set()
            for cid in candidates:
                cuid = fid_to_uid.get(cid)
                if cuid is None:
                    continue
                cgeom = uid_to_geom.get(cuid)
                if cgeom and cgeom.intersects(gap_geom):
                    touching_uids.add(cuid)
            if uid_a in touching_uids and uid_b in touching_uids:
                valid_gaps.append((gap_geom, uid_a, uid_b))

        Logger.log(
            f"GapFix: {len(valid_gaps)} valid gap(s), "
            f"{len(gap_zones) - len(valid_gaps)} exterior/artefact area(s) discarded.",
            level="INFO",
        )

        # --- Step 6: Merge valid gap zones into adjacent polygons ---
        gaps_merged = 0
        for gap_geom, uid_a, uid_b in valid_gaps:
            ga = uid_to_geom.get(uid_a)
            gb = uid_to_geom.get(uid_b)
            if ga is None or gb is None:
                continue

            # Assign to the neighbor with the longer shared boundary
            shared_a = ga.intersection(gap_geom)
            shared_b = gb.intersection(gap_geom)
            len_a = shared_a.length() if (shared_a and not shared_a.isEmpty()) else 0.0
            len_b = shared_b.length() if (shared_b and not shared_b.isEmpty()) else 0.0

            if len_a >= len_b:
                uid_to_geom[uid_a] = ga.combine(gap_geom)
            else:
                uid_to_geom[uid_b] = gb.combine(gap_geom)
            gaps_merged += 1

        Logger.log(f"GapFix: {gaps_merged} gap(s) merged into adjacent polygons.", level="INFO")

        # --- Build output memory layer ---
        crs = input_layer.crs()
        mem_uri = f"MultiPolygon?crs={crs.authid()}"
        out_layer = QgsVectorLayer(mem_uri, "gap_fix_result", "memory")
        provider = out_layer.dataProvider()
        provider.addAttributes(clean_polys.fields())
        out_layer.updateFields()

        out_feats = []
        for uid, g in uid_to_geom.items():
            f = uid_to_feat.get(uid)
            if f is None:
                continue
            out_f = QgsFeature(clean_polys.fields())
            out_f.setAttributes(f.attributes())
            out_f.setGeometry(g)
            out_feats.append(out_f)
        provider.addFeatures(out_feats)

        if debug_mode and workspace_path:
            save_debug_layer(out_layer, "GapFix", "gap_fix_result", workspace_path)

        Logger.log(f"GapFix End - Output features: {out_layer.featureCount()}", level="INFO")
        return out_layer

    except Exception as e:
        if debug_mode and workspace_path and isinstance(input_layer, QgsVectorLayer):
            save_debug_layer(input_layer, "GapFix", "exception_input", workspace_path, is_error=True)
        Logger.log(f"Error in GapFix: {str(e)}", level="CRITICAL")
        raise
