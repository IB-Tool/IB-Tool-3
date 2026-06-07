# -*- coding: utf-8 -*-
"""Remove building-free voids from settlement polygons.

For each settlement polygon, building footprints within the boundary are
selected and buffered by ``clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)``
metres. Areas inside the settlement that lie outside all building buffers are
treated as building-free voids and subtracted from the settlement.

Constants:
    _DEBUG_TOOL_NAME: Folder-name prefix for debug layer output, reflecting
        the call order in the main processing pipeline (``"09_ErodeEmptyAreas"``).
    MIN_BUFFER_M: Minimum per-building buffer distance in metres (10.0).
    MAX_BUFFER_M: Maximum per-building buffer distance in metres (100.0).
    MIN_EMPTY_AREA_M2: Minimum area (m²) of a building-free void to remove (500.0).
    TOPOLOGY_GRID_SIZE: Grid size for difference operations (0.00001).
"""

import math

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsProcessing,
)

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "09_ErodeEmptyAreas"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MIN_BUFFER_M = 10.0
"""Minimum per-building buffer distance (m). Applies to buildings with area ≤ 100 m²."""

MAX_BUFFER_M = 100.0
"""Maximum per-building buffer distance (m). Applies to buildings with area ≥ 10 000 m²."""

MIN_EMPTY_AREA_M2 = 500.0
"""Minimum area (m²) of a building-free void to remove. Smaller voids are kept."""

TOPOLOGY_GRID_SIZE = 0.00001
"""Grid size for difference operations (topology snapping)."""


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def erode_empty_areas(input_layer, buildings_layer,
                      min_empty_area=MIN_EMPTY_AREA_M2,
                      min_buffer_m=MIN_BUFFER_M,
                      max_buffer_m=MAX_BUFFER_M,
                      workspace_path=None,
                      debug_mode=False):
    """Remove building-free voids from a settlement polygon.

    Selects building footprints within ``input_layer``, buffers each by
    ``clamp(sqrt(building_area), min_buffer_m, max_buffer_m)`` metres,
    then subtracts any remaining uncovered area (voids) from the settlement.

    The input layer's attribute schema is preserved in the output.

    Requires QGIS >= 3.20. Both layers must use a metric CRS (metres).

    Args:
        input_layer: Settlement polygon layer (``QgsVectorLayer`` or file path).
            Must use a metric CRS.
        buildings_layer: Building footprint polygon layer (``QgsVectorLayer``).
        min_empty_area: Area threshold (m²). Building-free voids smaller than
            this are kept. Default: ``MIN_EMPTY_AREA_M2`` (500 m²).
        min_buffer_m: Minimum per-building buffer distance (m).
            Default: ``MIN_BUFFER_M`` (10 m).
        max_buffer_m: Maximum per-building buffer distance (m).
            Default: ``MAX_BUFFER_M`` (100 m).
        workspace_path: Absolute path for debug layer output. Ignored when
            ``debug_mode`` is ``False``.
        debug_mode: When ``True``, saves intermediate layers to
            ``workspace_path`` for visual inspection.

    Returns:
        A ``QgsVectorLayer`` with building-free voids (≥ ``min_empty_area``)
        removed from the settlement polygon. Returns ``input_layer`` unchanged
        when it has no valid features or when no buildings are found.

    Raises:
        Exception: Any unexpected processing error is logged at ``CRITICAL``
            level and re-raised after optionally saving a debug snapshot of
            the input layer.
    """
    Logger.log("ErodeEmptyAreas Start", level="INFO")
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path,
                tool_name=_DEBUG_TOOL_NAME)
    orig_layer = input_layer

    try:
        if isinstance(input_layer, str):
            input_layer = QgsVectorLayer(input_layer, "input", "ogr")

        # Early returns — no Processing invoked
        if not input_layer.isValid() or input_layer.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no valid input features, returning unchanged.",
                level="INFO",
            )
            return input_layer

        if not buildings_layer.isValid() or buildings_layer.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no buildings provided, returning input unchanged.",
                level="INFO",
            )
            return input_layer

        # --- Step 0: Fix input geometries ---
        fixed_input = safe_processing_run("native:fixgeometries", {
            'INPUT': input_layer,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(fixed_input, _DEBUG_TOOL_NAME,
                             "step0_fixed", workspace_path)

        # --- Step 1: Select buildings within settlement boundary ---
        Logger.log(
            "ErodeEmptyAreas: Step 1 – selecting buildings within settlement…",
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
            f"ErodeEmptyAreas: Step 2 – computing building buffers "
            f"(min={min_buffer_m} m, max={max_buffer_m} m)…",
            level="INFO",
        )
        buf_layer = _build_buffer_layer(sel_buildings, min_buffer_m, max_buffer_m)
        if debug_mode and workspace_path:
            save_debug_layer(buf_layer, _DEBUG_TOOL_NAME,
                             "step2_building_buffers", workspace_path)

        if buf_layer.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: all building geometries null/empty, returning unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 3: Dissolve buffer union ---
        # Uses collect + buffer(0, dissolve=True) workaround — native:dissolve
        # silently fails on large MultiPolygon datasets (QGIS ≤ 3.40).
        Logger.log(
            "ErodeEmptyAreas: Step 3 – dissolving buffer union…", level="INFO"
        )
        collected = safe_processing_run("native:collect", {
            'INPUT': buf_layer,
            'FIELD': [],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        buffer_union = safe_processing_run("native:buffer", {
            'INPUT': collected,
            'DISTANCE': 0,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': True,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(buffer_union, _DEBUG_TOOL_NAME,
                             "step3_buffer_union", workspace_path)

        # --- Step 4: Compute building-free voids ---
        Logger.log(
            "ErodeEmptyAreas: Step 4 – computing empty areas…", level="INFO"
        )
        empty_areas = safe_processing_run("native:difference", {
            'INPUT': fixed_input,
            'OVERLAY': buffer_union,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': TOPOLOGY_GRID_SIZE,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(empty_areas, _DEBUG_TOOL_NAME,
                             "step4_empty_areas", workspace_path)

        empty_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': empty_areas,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        filtered_empty = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': empty_single,
            'EXPRESSION': f'area($geometry) >= {min_empty_area}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(filtered_empty, _DEBUG_TOOL_NAME,
                             "step4_filtered_empty_areas", workspace_path)
        Logger.log(
            f"ErodeEmptyAreas: {filtered_empty.featureCount()} void(s) "
            f"(>= {min_empty_area} m²) to remove.",
            level="INFO",
        )

        if filtered_empty.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no voids to remove, returning input unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 5: Subtract voids from settlement ---
        Logger.log(
            "ErodeEmptyAreas: Step 5 – subtracting empty areas…", level="INFO"
        )
        result = safe_processing_run("native:difference", {
            'INPUT': fixed_input,
            'OVERLAY': filtered_empty,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': TOPOLOGY_GRID_SIZE,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(result, _DEBUG_TOOL_NAME,
                             "step5_result", workspace_path)

        Logger.log(
            f"ErodeEmptyAreas End – Output features: {result.featureCount()}",
            level="INFO",
        )
        return result

    except Exception as e:
        if debug_mode and workspace_path and isinstance(orig_layer, QgsVectorLayer):
            save_debug_layer(orig_layer, _DEBUG_TOOL_NAME, "exception_input",
                             workspace_path, is_error=True)
        Logger.log(f"Error in ErodeEmptyAreas: {str(e)}", level="CRITICAL")
        raise
