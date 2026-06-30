# -*- coding: utf-8 -*-
"""Close interior holes in settlement polygon layers up to a maximum hole area.

Dissolves the input, converts to boundary lines, polygonizes, identifies inner
holes, filters by area, and merges small holes back into the dissolved polygon.

Public API
----------
hole_close(input_layer, max_hole_size)
"""
from qgis.core import QgsProcessing, QgsVectorLayer
from qgis import processing

from ..helpers.geometry_utils import shp_area2, get_hole_polygons

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "HoleClose"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# QGIS extractbyattribute operator: area <= threshold (less than or equal)
_OPERATOR_LESS_THAN_OR_EQUAL: int = 5
"""QGIS extractbyattribute operator code for ``<= threshold`` comparisons."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hole_close(input_layer: QgsVectorLayer, max_hole_size: float) -> QgsVectorLayer:
    """Close holes inside a polygon layer up to a maximum hole area.

    Dissolves the input, converts to lines, polygonizes, identifies inner holes
    via :func:`get_hole_polygons`, filters by area, and merges the small holes
    back into the dissolved polygon to fill them.

    Args:
        input_layer: Input polygon layer (QgsVectorLayer).
        max_hole_size: Maximum hole area to close (e.g. in square metres).
            Holes with ``Area <= max_hole_size`` are filled.

    Returns:
        Polygon layer with holes up to ``max_hole_size`` filled (QgsVectorLayer).
    """
    input_layer_diss = processing.run("native:dissolve", {
        'INPUT': input_layer,
        'FIELD': [],
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    input_diss_line = processing.run("native:polygonstolines", {
        'INPUT': input_layer_diss,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    lines_poly = processing.run("native:polygonize", {
        'INPUT': input_diss_line,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    # Identify holes (polygons inside the dissolved outline but not part of it)
    holes = get_hole_polygons(lines_poly, input_layer_diss)

    shp_area2(holes)

    # Keep only holes smaller than or equal to the size threshold
    holes_filtered = processing.run("native:extractbyattribute", {
        'INPUT': holes,
        'FIELD': 'Area',
        'OPERATOR': _OPERATOR_LESS_THAN_OR_EQUAL,
        'VALUE': max_hole_size,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    # Merge filtered holes with the dissolved polygon to fill them
    merged_result = processing.run("qgis:mergevectorlayers", {
        "LAYERS": [holes_filtered, input_layer_diss],
        "CRS": input_layer.crs().authid(),
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    # Dissolve the merged result to produce the final closed polygon
    dissolved_result = processing.run("qgis:dissolve", {
        "INPUT": merged_result,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    return dissolved_result
