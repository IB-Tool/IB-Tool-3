# -*- coding: utf-8 -*-
"""Remove building-free voids from settlement polygons.

For each settlement polygon, building footprints are buffered by
``clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)`` metres. Areas
inside the settlement that lie outside all building buffers are treated as
building-free voids. Only building-free protrusions are removed: the voids
are temporarily subtracted from the settlement, and a void is removed when
less than ``MAX_BUILDING_CONTACT_PCT`` percent of its perimeter borders built
remainder parts (parts containing a building) and at least
``MIN_FREE_EDGE_PCT`` percent borders neither a built part nor another void.

Public API
----------
erode_empty_areas(input_layer, buildings_layer, min_empty_area, min_buffer_m,
                  max_buffer_m, max_building_contact_pct, min_free_edge_pct,
                  workspace_path, debug_mode)
"""

import math

from qgis import processing
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsProcessing,
    QgsSpatialIndex,
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

MAX_BUILDING_CONTACT_PCT = 20.0
"""Maximum share (%) of a void's perimeter that may border built settlement
parts for the void to be removed. Built parts are the pieces of
"settlement minus all voids" that contain at least one building."""

MIN_FREE_EDGE_PCT = 80.0
"""Minimum share (%) of a void's perimeter that must border neither a built
settlement part nor another void (i.e. open land at the outer boundary, or
unbuilt remainder pieces) for the void to be removed."""

_BOUNDARY_SNAP_M = 0.5
"""Buffer (m) around neighbouring geometries to catch near-touching edges."""


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


def _polygon_union(layer):
    """Union of all non-empty geometries in ``layer`` (None when there are none)."""
    geoms = [f.geometry() for f in layer.getFeatures()
             if f.geometry() and not f.geometry().isNull() and not f.geometry().isEmpty()]
    return QgsGeometry.unaryUnion(geoms) if geoms else None


def _built_parts(settlement_geom, void_geoms, buildings_layer):
    """Return the union of the remainder parts that contain a building.

    The voids are subtracted from the settlement only temporarily; the
    remainder is split into its parts and every part that intersects at
    least one building counts as built settlement.

    Returns:
        QgsGeometry, or None when no part contains a building.
    """
    remainder = settlement_geom.difference(QgsGeometry.unaryUnion(void_geoms))
    if remainder is None or remainder.isEmpty():
        return None

    index = QgsSpatialIndex()
    building_geoms = {}
    for feat in buildings_layer.getFeatures():
        geom = feat.geometry()
        if geom and not geom.isNull() and not geom.isEmpty():
            building_geoms[feat.id()] = geom
            index.addFeature(feat)

    built = []
    for part in remainder.asGeometryCollection():
        candidates = index.intersects(part.boundingBox())
        if any(part.intersects(building_geoms[fid]) for fid in candidates):
            built.append(part)
    return QgsGeometry.unaryUnion(built) if built else None


def _edge_shares(void_geom, built_strip, other_voids_strip):
    """Split a void's perimeter into building contact, void contact and free edge.

    Args:
        void_geom: Void polygon (QgsGeometry).
        built_strip: Built parts buffered by ``_BOUNDARY_SNAP_M`` (or None).
        other_voids_strip: Other voids buffered by ``_BOUNDARY_SNAP_M`` (or None).

    Returns:
        Tuple ``(building_pct, void_pct, free_pct)`` of the full perimeter
        (outer and inner rings).
    """
    edge = QgsGeometry(void_geom.constGet().boundary())
    perimeter = edge.length()
    if perimeter <= 0:
        return 0.0, 0.0, 0.0

    building_len = 0.0
    rest = edge
    if built_strip is not None:
        building_len = edge.intersection(built_strip).length()
        rest = edge.difference(built_strip)
    void_len = 0.0
    if other_voids_strip is not None and not rest.isEmpty():
        void_len = rest.intersection(other_voids_strip).length()
    free_len = max(0.0, perimeter - building_len - void_len)
    return (building_len / perimeter * 100, void_len / perimeter * 100,
            free_len / perimeter * 100)


def _protrusion_filter(settlement_layer, void_layer, buildings_layer,
                       max_building_contact_pct, min_free_edge_pct):
    """Return the voids that are building-free protrusions of the settlement.

    The voids are temporarily subtracted from the settlement; remainder parts
    containing a building are the built settlement. A void is returned for
    removal when less than ``max_building_contact_pct`` of its perimeter
    borders built parts AND at least ``min_free_edge_pct`` borders neither
    built parts nor another void. Interior voids (fully surrounded by built
    settlement) and voids between built parts are therefore kept.

    Args:
        settlement_layer: Settlement polygon (``QgsVectorLayer``).
        void_layer: Building-free void polygons (singlepart ``QgsVectorLayer``).
        buildings_layer: Building footprints within the settlement.
        max_building_contact_pct: Building contact must be strictly below this.
        min_free_edge_pct: Free edge must be at least this.

    Returns:
        ``QgsVectorLayer`` (Polygon, memory) with the voids to remove; empty
        when no void qualifies.
    """
    crs_id = void_layer.crs().authid()
    out = QgsVectorLayer(f"Polygon?crs={crs_id}", "voids_to_remove", "memory")

    settlement_geom = _polygon_union(settlement_layer)
    voids = [f.geometry() for f in void_layer.getFeatures()
             if f.geometry() and not f.geometry().isNull() and not f.geometry().isEmpty()]
    if settlement_geom is None or not voids:
        return out

    built = _built_parts(settlement_geom, voids, buildings_layer)
    built_strip = built.buffer(_BOUNDARY_SNAP_M, 5) if built is not None else None
    void_strips = [v.buffer(_BOUNDARY_SNAP_M, 5) for v in voids]

    selected = []
    for i, void in enumerate(voids):
        others = [s for j, s in enumerate(void_strips)
                  if j != i and s.boundingBoxIntersects(void_strips[i])]
        others_strip = QgsGeometry.unaryUnion(others) if others else None
        building_pct, void_pct, free_pct = _edge_shares(void, built_strip, others_strip)
        remove = building_pct < max_building_contact_pct and free_pct >= min_free_edge_pct
        Logger.log(
            f"ErodeEmptyAreas: void {i}: building {building_pct:.1f} %, "
            f"void {void_pct:.1f} %, free {free_pct:.1f} % -> "
            f"{'removed' if remove else 'kept'}",
            level="INFO",
        )
        if remove:
            feat = QgsFeature()
            feat.setGeometry(void)
            selected.append(feat)

    out.dataProvider().addFeatures(selected)
    return out


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
                      max_building_contact_pct=MAX_BUILDING_CONTACT_PCT,
                      min_free_edge_pct=MIN_FREE_EDGE_PCT,
                      workspace_path=None,
                      debug_mode=False):
    """Remove building-free voids from a settlement polygon.
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
        max_building_contact_pct: A void is removed only when less than this
            share (%) of its perimeter borders built settlement parts.
            Default: ``MAX_BUILDING_CONTACT_PCT`` (20 %).
        min_free_edge_pct: A void is removed only when at least this share (%)
            of its perimeter borders neither built parts nor another void.
            Default: ``MIN_FREE_EDGE_PCT`` (80 %).
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

        # --- Step 4b: Protrusion filter ---
        # Only remove building-free protrusions: voids that border built
        # settlement parts by less than max_building_contact_pct % and are free
        # (no built part, no other void) along at least min_free_edge_pct %.
        Logger.log(
            f"ErodeEmptyAreas: Step 4b - protrusion filter "
            f"(building contact < {max_building_contact_pct}%, "
            f"free edge >= {min_free_edge_pct}%)...",
            level="INFO",
        )
        voids_to_remove = _protrusion_filter(
            fixed_input, filtered_empty, sel_buildings,
            max_building_contact_pct, min_free_edge_pct)
        Logger.log(
            f"ErodeEmptyAreas: {voids_to_remove.featureCount()} void(s) to remove; "
            f"{filtered_empty.featureCount() - voids_to_remove.featureCount()} kept.",
            level="INFO",
        )
        if debug_mode and workspace_path:
            save_debug_layer(voids_to_remove, _DEBUG_TOOL_NAME,
                             "step4b_voids_to_remove", workspace_path)

        if voids_to_remove.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no voids qualify after protrusion filter, "
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
