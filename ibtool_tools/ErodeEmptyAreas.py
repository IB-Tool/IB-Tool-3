# -*- coding: utf-8 -*-
"""Remove building-free voids from settlement polygons.

For each settlement polygon, building footprints within the boundary are
selected and buffered by ``clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)``
metres. Areas inside the settlement that lie outside all building buffers are
treated as building-free voids. Only voids where less than
``BOUNDARY_CONTACT_THRESHOLD_PCT`` percent of their boundary coincides with
the settlement's outer boundary are removed. Interior voids with high or zero
outer-boundary contact are left intact.

Constants:
    _DEBUG_TOOL_NAME: Folder-name prefix for debug layer output, reflecting
        the call order in the main processing pipeline (``"06_ErodeEmptyAreas"``).
    MIN_BUFFER_M: Minimum per-building buffer distance in metres (10.0).
    MAX_BUFFER_M: Maximum per-building buffer distance in metres (100.0).
    MIN_EMPTY_AREA_M2: Minimum area (m2) of a building-free void to consider (500.0).
    TOPOLOGY_GRID_SIZE: Grid size for difference operations (0.001).
    BOUNDARY_CONTACT_THRESHOLD_PCT: Maximum fraction (%) of a void's boundary
        that may touch the settlement outer boundary for the void to be removed
        (20.0). Voids at or above this threshold are kept.
    _BOUNDARY_SEGMENT_M: Segment length (m) used when splitting void boundaries
        for the contact-fraction measurement (10.0).
    _BOUNDARY_SNAP_M: Buffer distance (m) around the settlement boundary used
        to catch near-touching void segments (0.5).
"""

import math

from qgis import processing
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsProcessing,
)

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name -- prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "06_ErodeEmptyAreas"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MIN_BUFFER_M = 10.0
"""Minimum per-building buffer distance (m). Applies to buildings with area <= 100 m2."""

MAX_BUFFER_M = 100.0
"""Maximum per-building buffer distance (m). Applies to buildings with area >= 10 000 m2."""

MIN_EMPTY_AREA_M2 = 500.0
"""Minimum area (m2) of a building-free void to remove. Smaller voids are kept."""

TOPOLOGY_GRID_SIZE = 0.001
"""Grid size for difference operations (topology snapping).

1 mm (vs 10 um used elsewhere): the finer 10 um grid can snap sub-millimetre
void slivers to zero, producing degenerate output geometries. 1 mm is coarse
enough to remove floating-point noise while preserving meaningful voids."""

BOUNDARY_CONTACT_THRESHOLD_PCT = 20.0
"""Maximum fraction (%) of a void's boundary touching the settlement outer
boundary for the void to be removed. Only voids whose contact is strictly
below this threshold are eroded away; voids with higher contact are kept."""

_BOUNDARY_SEGMENT_M = 10.0
"""Segment length (m) for splitting void boundaries during contact measurement."""

_BOUNDARY_SNAP_M = 0.5
"""Buffer (m) around the settlement boundary to catch near-touching segments."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_buffer_layer(sel_buildings, min_buffer_m, max_buffer_m):
    """Build a memory layer of per-building buffer polygons.

    Buffer distance per building: ``clamp(sqrt(area), min_buffer_m, max_buffer_m)``.

    Args:
        sel_buildings: QgsVectorLayer of building footprints.
        min_buffer_m: Minimum buffer distance in metres.
        max_buffer_m: Maximum buffer distance in metres.

    Returns:
        QgsVectorLayer (memory, Polygon) with one buffer feature per building.
        May have 0 features if all building geometries are null/empty.
    """
    crs = sel_buildings.crs()
    mem_uri = f"Polygon?crs={crs.authid()}"
    buf_layer = QgsVectorLayer(mem_uri, "building_buffers", "memory")
    provider = buf_layer.dataProvider()

    buf_feats = []
    for feat in sel_buildings.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isNull() or geom.isEmpty():
            continue
        area = geom.area()
        buf_dist = max(min_buffer_m, min(max_buffer_m, math.sqrt(area)))
        buf_geom = geom.buffer(buf_dist, 5)
        if buf_geom and not buf_geom.isEmpty():
            f = QgsFeature()
            f.setGeometry(buf_geom)
            buf_feats.append(f)

    provider.addFeatures(buf_feats)
    return buf_layer


def _settlement_outer_buffer(settlement_layer, void_layer):
    """Build a buffered strip around the settlement's outer boundary only.

    Deletes interior rings before converting to lines so that inner-ring edges
    (which border existing holes) are excluded from the reference boundary.

    Returns:
        QgsVectorLayer (Polygon) — thin buffer strip around the outer boundary.
    """
    settlement_no_holes = safe_processing_run("native:deleteholes", {
        'INPUT': settlement_layer,
        'MIN_AREA': 0,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    settlement_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': settlement_no_holes,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    void_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': void_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    settlement_diff = safe_processing_run("native:difference", {
        'INPUT': settlement_fixed,
        'OVERLAY': void_fixed,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    })['OUTPUT']

    settlement_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': settlement_diff,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    return safe_processing_run("native:buffer", {
        'INPUT': settlement_lines,
        'DISTANCE': _BOUNDARY_SNAP_M,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _void_split_lines(void_with_fid):
    """Convert void polygons to length-annotated boundary line segments.

    Returns:
        QgsVectorLayer of short line segments with ``fid_copy`` and
        ``length_1`` (total perimeter of the parent void) attributes.
    """
    void_lines = safe_processing_run("native:polygonstolines", {
        'INPUT': void_with_fid,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    void_lines_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': void_lines,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    void_lines_length = safe_processing_run("qgis:fieldcalculator", {
        'INPUT': void_lines_single,
        'FIELD_NAME': 'length_1',
        'FIELD_TYPE': 0,
        'FIELD_LENGTH': 20,
        'FIELD_PRECISION': 10,
        'NEW_FIELD': True,
        'FORMULA': '$length',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    return safe_processing_run("native:splitlinesbylength", {
        'INPUT': void_lines_length,
        'LENGTH': _BOUNDARY_SEGMENT_M,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _contact_fraction_filter(settlement_layer, void_layer, threshold_pct):
    """Return void polygons whose boundary-contact with the settlement outer
    boundary is strictly below threshold_pct.

    Measures the fraction of each void's perimeter that coincides with the
    settlement polygon's exterior boundary only. Interior ring lines (edges
    of existing holes) are excluded by deleting holes from the settlement before
    converting to lines -- otherwise voids inside existing holes would show high
    contact with those inner-ring lines and would never be selected for removal.

    Only voids whose contact fraction is strictly below the threshold are
    returned as polygon features for removal. Interior voids (0 % contact)
    never appear in the overlap result and are never returned.

    Args:
        settlement_layer: Settlement polygon (``QgsVectorLayer``).
        void_layer: Building-free void polygons (singlepart ``QgsVectorLayer``).
        threshold_pct: Contact fraction threshold in percent. Only voids with
            contact strictly below this value are returned for removal.

    Returns:
        ``QgsVectorLayer`` (Polygon) containing void polygons whose
        boundary-contact fraction with the settlement outer boundary is
        strictly below ``threshold_pct``. Returns an empty polygon layer when
        no voids qualify.
    """
    # Step 1: Assign stable fid_copy to void POLYGONS before converting to lines
    # so that IDs survive all intermediate processing steps and can be used
    # to select the original polygon features at the end.
    void_with_fid = safe_processing_run("native:fieldcalculator", {
        'INPUT': void_layer,
        'FIELD_NAME': 'fid_copy',
        'FIELD_TYPE': 0,
        'FIELD_LENGTH': 0,
        'FIELD_PRECISION': 0,
        'FORMULA': '@id',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    # Steps 2-5: Settlement outer boundary buffer + void boundary split lines
    settlement_buff = _settlement_outer_buffer(settlement_layer, void_layer)
    split_lines = _void_split_lines(void_with_fid)

    # Step 6: Select void segments that touch the settlement outer boundary
    overlapping = safe_processing_run("native:extractbylocation", {
        'INPUT': split_lines,
        'PREDICATE': [0],  # intersects
        'INTERSECT': settlement_buff,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    if overlapping.featureCount() == 0:
        Logger.log(
            "_contact_fraction_filter: no void boundary segments touch settlement "
            "outer boundary -> all voids are interior, none qualify for removal.",
            level="INFO",
        )
        return QgsVectorLayer(
            f"Polygon?crs={void_layer.crs().authid()}", "empty", "memory")

    # Step 7: Sum overlapping segment lengths per void (length_2)
    dissolved_overlap = safe_processing_run("qgis:dissolve", {
        'INPUT': overlapping,
        'FIELD': ['fid_copy'],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    with_length_2 = safe_processing_run("qgis:fieldcalculator", {
        'INPUT': dissolved_overlap,
        'FIELD_NAME': 'length_2',
        'FIELD_TYPE': 0,
        'FIELD_LENGTH': 20,
        'FIELD_PRECISION': 10,
        'NEW_FIELD': True,
        'FORMULA': '$length',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    # Step 8: Find fid_copy values whose contact fraction is below the threshold
    qualifying_lines = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': with_length_2,
        'EXPRESSION': f'("length_2" / "length_1") * 100 < {threshold_pct}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    if qualifying_lines.featureCount() == 0:
        return QgsVectorLayer(
            f"Polygon?crs={void_layer.crs().authid()}", "empty", "memory")

    # Step 9: Select matching POLYGON features from void_with_fid using the
    # qualifying fid_copy values -- return polygons, not line segments.
    fid_values = [f['fid_copy'] for f in qualifying_lines.getFeatures()]
    fid_list = ','.join(str(int(v)) for v in fid_values)
    return safe_processing_run("qgis:extractbyexpression", {
        'INPUT': void_with_fid,
        'EXPRESSION': f'"fid_copy" IN ({fid_list})',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _dissolve_union(input_layer, debug_mode=False, workspace_path=None):
    """Dissolves all features into a single geometry using a safe union workaround.

    Applies ``fix -> collect -> buffer(0, dissolve=True)`` instead of
    ``native:dissolve`` to avoid the GEOS bug that silently produces empty
    or null geometry on large MultiPolygon datasets.

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        debug_mode: If True, debug files may be saved on processing errors.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer with all features dissolved into one geometry.
    """
    _dbg = {"debug_mode": debug_mode, "workspace_path": workspace_path,
            "tool_name": _DEBUG_TOOL_NAME}

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


def _dissolve_to_single_feature(fixed_input, debug_mode=False, workspace_path=None):
    """Combine all polygon features into one MultiPolygon via QgsGeometry.combine().

    Uses direct GEOS union (no feature-sink write) to avoid mixed-geometry-type
    errors that arise when native:collect receives Polygon + MultiPolygon input.

    Returns:
        QgsVectorLayer with a single dissolved feature, or ``None`` when all
        input features are degenerate or non-polygon.
    """
    diss_geom = QgsGeometry()
    for feat in fixed_input.getFeatures():
        geom = feat.geometry()
        if not geom or geom.isNull() or geom.isEmpty():
            continue
        if QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry:
            continue
        if diss_geom.isNull():
            diss_geom = QgsGeometry(geom)
        else:
            diss_geom = diss_geom.combine(geom)

    if diss_geom.isNull() or diss_geom.isEmpty():
        return None

    if not QgsWkbTypes.isMultiType(diss_geom.wkbType()):
        diss_geom.convertToMultiType()

    diss_layer = QgsVectorLayer(
        f"MultiPolygon?crs={fixed_input.crs().authid()}", "dissolved_input", "memory"
    )
    diss_feat = QgsFeature()
    diss_feat.setGeometry(diss_geom)
    diss_layer.dataProvider().addFeatures([diss_feat])
    if debug_mode and workspace_path:
        save_debug_layer(diss_layer, _DEBUG_TOOL_NAME, "step0b_dissolved", workspace_path)
    return diss_layer


def _build_buffer_union_layer(buf_layer, crs_id, debug_mode=False, workspace_path=None):
    """Union all building buffer geometries into a single MultiPolygon layer.

    Uses ``QgsGeometry.unaryUnion()`` to avoid QGIS feature-sink issues with
    mixed Polygon/MultiPolygon input from buffered multi-part buildings.

    Returns:
        QgsVectorLayer or ``None`` when no valid buffer geometries are found.
    """
    buf_geoms = [
        bf.geometry() for bf in buf_layer.getFeatures()
        if bf.geometry() and not bf.geometry().isNull() and not bf.geometry().isEmpty()
    ]
    if not buf_geoms:
        return None

    union_geom = QgsGeometry.unaryUnion(buf_geoms)
    if union_geom.isNull() or union_geom.isEmpty():
        return None

    if not QgsWkbTypes.isMultiType(union_geom.wkbType()):
        union_geom.convertToMultiType()

    union_layer = QgsVectorLayer(f"MultiPolygon?crs={crs_id}", "buffer_union", "memory")
    bu_feat = QgsFeature()
    bu_feat.setGeometry(union_geom)
    union_layer.dataProvider().addFeatures([bu_feat])
    if debug_mode and workspace_path:
        save_debug_layer(union_layer, _DEBUG_TOOL_NAME, "step3_buffer_union", workspace_path)
    return union_layer


def _compute_void_candidates(fixed_input, buffer_union, min_empty_area,
                              debug_mode=False, workspace_path=None):
    """Compute building-free void polygons that exceed ``min_empty_area``.

    Args:
        fixed_input: Dissolved settlement layer (QgsVectorLayer).
        buffer_union: Union of building buffers (QgsVectorLayer).
        min_empty_area: Minimum void area in m2.
        debug_mode: Save intermediate debug layers when True.
        workspace_path: Base path for debug output.

    Returns:
        QgsVectorLayer of void polygon candidates.
    """
    _dbg = {"debug_mode": debug_mode, "workspace_path": workspace_path,
            "tool_name": _DEBUG_TOOL_NAME}
    empty_areas = safe_processing_run("native:difference", {
        'INPUT': fixed_input,
        'OVERLAY': buffer_union,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': TOPOLOGY_GRID_SIZE,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(empty_areas, _DEBUG_TOOL_NAME, "step4_empty_areas", workspace_path)

    empty_single = safe_processing_run("native:multiparttosingleparts", {
        'INPUT': empty_areas,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    filtered = safe_processing_run("qgis:extractbyexpression", {
        'INPUT': empty_single,
        'EXPRESSION': f'area($geometry) >= {min_empty_area}',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(filtered, _DEBUG_TOOL_NAME,
                         "step4_filtered_empty_areas", workspace_path)
    return filtered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def erode_empty_areas(input_layer, buildings_layer,  # pylint: disable=too-many-arguments
                      min_empty_area=MIN_EMPTY_AREA_M2,
                      min_buffer_m=MIN_BUFFER_M,
                      max_buffer_m=MAX_BUFFER_M,
                      contact_threshold_pct=BOUNDARY_CONTACT_THRESHOLD_PCT,
                      workspace_path=None,
                      debug_mode=False):
    """Remove building-free voids from a settlement polygon.

    Selects building footprints within ``input_layer``, buffers each by
    ``clamp(sqrt(building_area), min_buffer_m, max_buffer_m)`` metres, then
    identifies uncovered areas (voids) inside the settlement. A void is only
    removed if less than ``contact_threshold_pct`` percent of its boundary
    coincides with the settlement's outer boundary -- voids at or above the
    threshold border the settlement significantly and are left intact.

    The input layer's attribute schema is preserved in the output.

    Requires QGIS >= 3.20. Both layers must use a metric CRS (metres).

    Args:
        input_layer: Settlement polygon layer (``QgsVectorLayer`` or file path).
            Must use a metric CRS.
        buildings_layer: Building footprint polygon layer (``QgsVectorLayer``).
        min_empty_area: Area threshold (m2). Building-free voids smaller than
            this are kept. Default: ``MIN_EMPTY_AREA_M2`` (500 m2).
        min_buffer_m: Minimum per-building buffer distance (m).
            Default: ``MIN_BUFFER_M`` (10 m).
        max_buffer_m: Maximum per-building buffer distance (m).
            Default: ``MAX_BUFFER_M`` (100 m).
        contact_threshold_pct: Maximum share (%) of a void's boundary that may
            touch the settlement outer boundary for the void to be removed.
            Voids with equal or higher contact are kept.
            Default: ``BOUNDARY_CONTACT_THRESHOLD_PCT`` (20 %).
        workspace_path: Absolute path for debug layer output. Ignored when
            ``debug_mode`` is ``False``.
        debug_mode: When ``True``, saves intermediate layers to
            ``workspace_path`` for visual inspection.

    Returns:
        A ``QgsVectorLayer`` with qualifying building-free voids removed from
        the settlement polygon. Returns ``input_layer`` unchanged when it has
        no valid features or when no buildings are found.

    Raises:
        Exception: Any unexpected processing error is logged at ``CRITICAL``
            level and re-raised after optionally saving a debug snapshot of
            the input layer.
    """
    Logger.log("ErodeEmptyAreas Start", level="INFO")
    _dbg = {"debug_mode": debug_mode, "workspace_path": workspace_path,
            "tool_name": _DEBUG_TOOL_NAME}
    orig_layer = input_layer

    if not input_layer.isValid():
        Logger.log("ErodeEmptyAreas: invalid input layer, returning unchanged.", level="INFO")
        return input_layer

    try:
        # Fix geometries and dissolve all features into one (safe workaround for GEOS bug)
        fixed_input = _dissolve_union(input_layer, debug_mode=debug_mode,
                                     workspace_path=workspace_path)

        if not fixed_input.isValid() or fixed_input.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no valid input features, returning unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 0b: Python-level dissolve to eliminate overlapping features ---
        # blocks_merge contains overlapping snapped_rect + blocks_dense features
        # whose coincident edges cause native:difference to produce a
        # GeometryCollection output QGIS cannot write. native:collect on the same
        # input also fails (same "Konnte Objekt nicht schreiben") because
        # fixgeometries can transform degenerate polygons into Lines/Points,
        # leaving mixed geometry types that mismatch the output sink.
        # Using QgsGeometry.combine() (direct GEOS union, no feature-sink write)
        # avoids both failure modes and always yields a clean Polygon/MultiPolygon.
        fixed_input = _dissolve_to_single_feature(fixed_input, debug_mode, workspace_path)
        if fixed_input is None:
            Logger.log(
                "ErodeEmptyAreas: all input features degenerate after fixgeometries; "
                "returning input unchanged.",
                level="WARNING",
            )
            return orig_layer

        # --- Step 1: Select buildings within settlement boundary ---
        Logger.log(
            "ErodeEmptyAreas: Step 1 - selecting buildings within settlement...",
            level="INFO",
        )
        sel_buildings = safe_processing_run("native:extractbylocation", {
            'INPUT': buildings_layer,
            'PREDICATE': [0],   # intersects
            'INTERSECT': fixed_input,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(sel_buildings, _DEBUG_TOOL_NAME,
                             "step1_sel_buildings", workspace_path)
        Logger.log(
            f"ErodeEmptyAreas: {sel_buildings.featureCount()} building(s) selected.",
            level="INFO",
        )

        if sel_buildings.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no buildings within settlement, returning unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 2: Build per-building buffer layer ---
        Logger.log(
            f"ErodeEmptyAreas: Step 2 - computing building buffers "
            f"(min={min_buffer_m} m, max={max_buffer_m} m)...",
            level="INFO",
        )
        buf_layer = _build_buffer_layer(sel_buildings, min_buffer_m, max_buffer_m)
        if debug_mode and workspace_path:
            save_debug_layer(buf_layer, _DEBUG_TOOL_NAME,
                             "step2_building_buffers", workspace_path)

        # --- Step 3: Build buffer union ---
        Logger.log(
            "ErodeEmptyAreas: Step 3 - dissolving buffer union...", level="INFO"
        )
        buffer_union = _build_buffer_union_layer(
            buf_layer, fixed_input.crs().authid(), debug_mode, workspace_path)
        if buffer_union is None:
            Logger.log(
                "ErodeEmptyAreas: no valid building buffers or empty union, "
                "returning unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 4: Compute building-free voids ---
        Logger.log(
            "ErodeEmptyAreas: Step 4 - computing empty areas...", level="INFO"
        )
        filtered_empty = _compute_void_candidates(
            fixed_input, buffer_union, min_empty_area, debug_mode, workspace_path)
        Logger.log(
            f"ErodeEmptyAreas: {filtered_empty.featureCount()} void candidate(s) "
            f"(>= {min_empty_area} m2), contact filter follows.",
            level="INFO",
        )

        if filtered_empty.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no voids to remove, returning input unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 4b: Contact-fraction filter ---
        # Only remove voids whose boundary touches the settlement outer boundary
        # by less than contact_threshold_pct %. Voids at or above this threshold
        # border the settlement significantly and are left intact.
        Logger.log(
            f"ErodeEmptyAreas: Step 4b - contact fraction filter "
            f"(threshold={contact_threshold_pct}%)...",
            level="INFO",
        )
        voids_to_remove = _contact_fraction_filter(
            fixed_input, filtered_empty, contact_threshold_pct)
        Logger.log(
            f"ErodeEmptyAreas: {voids_to_remove.featureCount()} void(s) to remove "
            f"(contact < {contact_threshold_pct}%); "
            f"{filtered_empty.featureCount() - voids_to_remove.featureCount()} kept.",
            level="INFO",
        )
        if debug_mode and workspace_path:
            save_debug_layer(voids_to_remove, _DEBUG_TOOL_NAME,
                             "step4b_voids_to_remove", workspace_path)

        if voids_to_remove.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no voids qualify after contact filter, "
                "returning input unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 5: Subtract voids from settlement ---
        Logger.log(
            "ErodeEmptyAreas: Step 5 - subtracting empty areas...", level="INFO"
        )

        voids_to_remove_buff = processing.run("native:buffer", {
            'INPUT': voids_to_remove,
            'DISTANCE': 0.5,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 1,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': False,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

        result = safe_processing_run("native:difference", {
            'INPUT': fixed_input,
            'OVERLAY': voids_to_remove_buff,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': TOPOLOGY_GRID_SIZE,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(result, _DEBUG_TOOL_NAME, "step5_result", workspace_path)

        Logger.log(
            f"ErodeEmptyAreas End - Output features: {result.featureCount()}",
            level="INFO",
        )
        return result

    except Exception as e:
        if debug_mode and workspace_path and isinstance(orig_layer, QgsVectorLayer):
            save_debug_layer(orig_layer, _DEBUG_TOOL_NAME, "exception_input",
                             workspace_path, is_error=True)
        Logger.log(f"Error in ErodeEmptyAreas: {str(e)}", level="CRITICAL")
        raise
