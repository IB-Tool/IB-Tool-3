"""Gap-fixing tool for the IBTool plugin.

Closes narrow gaps between adjacent polygon settlement features and removes
interior holes (inner rings). Operates entirely in memory using QGIS Processing
algorithms and a pure-Python pairwise spatial-index intersection step.

Constants:
    _DEBUG_TOOL_NAME: Folder-name prefix for debug layer output, reflecting the
        call order in the main processing pipeline (``"08_GapFix"``).
"""

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsSpatialIndex,
    QgsProcessing,
)

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "08_GapFix"


def gap_fix(Inputpoly, InputRoadnetwork=None, workspace_path=None,  # pylint: disable=invalid-name
            bufferwidth=70, max_gap=10.0, debug_mode=False,
            erosion_width=None, linearity_area_fraction=0.7):
    """Close inter-polygon gaps and remove interior holes from a polygon layer.

    Applies a seven-step algorithm:

    1. Fix geometries (``native:fixgeometries``).
    2. Close interior holes: polygons → lines → polygonize → collect +
       buffer(0, dissolve=True). Produces hole-free, merged polygons.
    3. Multipart → singlepart; assign unique integer field ``gap_uid``.
    4. Build *donut* buffer rings per polygon: buffer by ``max_gap``,
       then subtract all original polygons. Rings cover only empty space.
    5. Pairwise intersect buffer rings via a spatial index.
       Each intersection area is a gap-zone candidate between two polygons.
    6. Validate candidates: keep only gap zones that geometrically intersect
       *both* source polygons. Exterior fringes and artefacts are discarded.
    7. Merge each valid gap zone into the neighbor with the longer shared
       boundary; rebuild a memory output layer.

    Note on attributes: the global dissolve in step 2 rebuilds polygon
    topology, so original feature attributes are replaced by ``gap_uid``.

    Note on ``native:dissolve``: intentionally avoided — it silently fails on
    large MultiPolygon datasets. The workaround ``native:collect`` +
    ``native:buffer(distance=0, dissolve=True)`` is used throughout.

    Requires QGIS >= 3.20. The input layer must use a metric CRS (meters).

    Args:
        Inputpoly: Input polygon layer as a ``QgsVectorLayer`` or a file-path
            string. Must use a metric CRS.
        InputRoadnetwork: Unused; kept for API compatibility.
        workspace_path: Absolute path to the workspace directory used for
            debug layer output. Ignored when ``debug_mode`` is ``False``.
        bufferwidth: Unused; kept for API compatibility.
        max_gap: Buffer distance in meters. Defines the maximum gap width that
            will be closed between neighboring polygons.
        debug_mode: When ``True``, saves intermediate layers to
            ``workspace_path`` for visual inspection.
        erosion_width: Inward erosion applied to each gap zone to measure
            linearity. Defaults to ``max_gap / 2`` when ``None``. A gap zone
            is kept only if ``frac_removed >= linearity_area_fraction``.
        linearity_area_fraction: Minimum fraction of gap zone area that must
            be removed by erosion for the gap to be classified as linear and
            merged. ``0.0`` disables the filter (all valid gaps are merged,
            reproducing legacy behaviour). Default ``0.7``.

    Returns:
        A memory ``QgsVectorLayer`` (geometry type ``MultiPolygon``) with
        interior holes removed and inter-polygon gaps up to ``max_gap`` filled.
        Returns the (possibly invalid) input layer unchanged if it has no
        valid features.

    Raises:
        Exception: Any unexpected processing error is logged at ``CRITICAL``
            level and re-raised after optionally saving a debug snapshot of the
            input layer.
    """
    Logger.log("GapFix Start", level="INFO")
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)
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
            save_debug_layer(fixed, _DEBUG_TOOL_NAME, "step0_fixed", workspace_path)

        # --- Step 2: Multipart → singlepart + unique ID field ---
        Logger.log("GapFix: Step 2 – singleparts and unique IDs…", level="INFO")

        singleparts = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': fixed,
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
            save_debug_layer(clean_polys, _DEBUG_TOOL_NAME, "step2_clean_polys", workspace_path)

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
            save_debug_layer(buffer_rings, _DEBUG_TOOL_NAME, "step3_buffer_rings", workspace_path)

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

        # --- Step 5b: Linearity filter ---
        # Keep only gap zones whose shape is narrow/linear: erode by erosion_width,
        # compute frac_removed = 1 - eroded_area/original_area. Blocky zones
        # (large remaining area after erosion) are discarded.
        if linearity_area_fraction > 0:
            eff_erosion = erosion_width if erosion_width is not None else max_gap / 2
            filtered = []
            for gap_geom, uid_a, uid_b in valid_gaps:
                orig_area = gap_geom.area()
                if orig_area <= 0:
                    continue
                eroded = gap_geom.buffer(-eff_erosion, 5)
                eroded_area = eroded.area() if (eroded and not eroded.isEmpty()) else 0.0
                frac_removed = 1.0 - (eroded_area / orig_area)
                if frac_removed >= linearity_area_fraction:
                    filtered.append((gap_geom, uid_a, uid_b))
            Logger.log(
                f"GapFix: Step 5b – {len(filtered)} linear gap(s) kept, "
                f"{len(valid_gaps) - len(filtered)} blocky zone(s) discarded.",
                level="INFO",
            )
            valid_gaps = filtered

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
            save_debug_layer(out_layer, _DEBUG_TOOL_NAME, "gap_fix_result", workspace_path)

        Logger.log(f"GapFix End - Output features: {out_layer.featureCount()}", level="INFO")
        return out_layer

    except Exception as e:
        if debug_mode and workspace_path and isinstance(input_layer, QgsVectorLayer):
            save_debug_layer(input_layer, _DEBUG_TOOL_NAME, "exception_input", workspace_path, is_error=True)
        Logger.log(f"Error in GapFix: {str(e)}", level="CRITICAL")
        raise
