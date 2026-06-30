# -*- coding: utf-8 -*-
"""Import filter for building footprints based on ATKIS function codes and density analysis.

Reads a filter definition file to build positive and negative QGIS selection
expressions, then applies a multi-step filter pipeline (function type, kernel
density, minimum area) to the input building layer.

Public API
----------
import_filter(filename, hu_layer)
input_hu_filter(hu_layer, filter_file, min_area, cell_size, neighborhood_radius,
                debug_mode, workspace_path)
"""

from __future__ import annotations

import os

from qgis.core import QgsWkbTypes, QgsVectorLayer, QgsProcessingUtils
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.geometry_utils import select_and_save_by_location, shp_area, shp_area2
from ..helpers.debug_utils import save_debug_layer

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "02_ImportFilter"

# Number of characters taken from each filter-file entry for the ATKIS code match.
_FILTER_CODE_LENGTH = 10

# Minimum heatmap density value for a raster point to define a residential zone.
_MIN_DENSITY_VALUE = 4

# Divisor applied to cell_size to compute the buffer radius around density points.
_BUFFER_CELL_DIVISOR = 1.5

# Minimum individual building area (sqm) retained in the final output layer.
_MIN_BUILDING_AREA = 35


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _create_filter_string(filter_list: list[str], fieldname: str) -> str:
    """Build a QGIS expression string that matches features by LIKE comparisons.

    Joins every entry in ``filter_list`` with OR to produce an expression like::

        fkt LIKE '31001_1000' OR fkt LIKE '31001_1010'

    Args:
        filter_list: Quoted ATKIS code strings (e.g. ``["'31001_1000'"]``).
        fieldname: Attribute field name to match against.

    Returns:
        A QGIS expression string, or an empty string if ``filter_list`` is empty.
    """
    parts = [f"{fieldname} LIKE {value}" for value in filter_list]
    return " OR ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_filter(
    filename: str, hu_layer: QgsVectorLayer
) -> tuple[str, str, str]:
    """Read a filter definition file and build QGIS selection expressions.

    Parses the filter file into positive and negative code lists, then
    assembles LIKE-based selection strings for later feature extraction.

    Args:
        filename: Path to the filter definition text file.
        hu_layer: Building footprint polygon layer. Must have a ``fkt``,
            ``gfkzshh`` or ``funktion`` attribute field.

    Returns:
        Tuple of ``(filter_positive, filter_negative, fieldname)`` where both
        filter strings are QGIS expression strings.

    Raises:
        ValueError: If the file does not exist, the layer is invalid, or the
            required attribute field is missing.
    """
    if not os.path.isfile(filename):
        raise ValueError(f"{filename} existiert nicht im Arbeitsverzeichnis.")

    # Validate input layer geometry type
    if not hu_layer.isValid() or hu_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError("hu_layer must be a valid polygon layer.")

    # Determine attribute field name
    fieldname = None
    fields = hu_layer.fields()
    if fields.indexOf("fkt") != -1:
        fieldname = "fkt"
    elif fields.indexOf("gfkzshh") != -1:
        fieldname = "gfkzshh"
    elif fields.indexOf("funktion") != -1:
        fieldname = "funktion"
    else:
        raise ValueError("Der Eingabelayer hat weder ein 'fkt', 'gfkzshh'- noch ein 'funktion'-Feld.")

    # Read filter file and build entry lists
    with open(filename, 'r', encoding='utf-8') as file:
        pos_entries = []
        neg_entries = []
        current_section = None

        for row in file:
            row = row.strip()
            if row.startswith("#Filter positive"):
                current_section = "positive"
            elif row.startswith("#Filter negative"):
                current_section = "negative"
            elif row.startswith("#") or not row:
                continue
            else:
                if current_section == "positive":
                    pos_entries.append(f"'{row[:_FILTER_CODE_LENGTH]}'")
                elif current_section == "negative":
                    neg_entries.append(f"'{row[:_FILTER_CODE_LENGTH]}'")

    filterpos = _create_filter_string(pos_entries, fieldname)
    filterneg = _create_filter_string(neg_entries, fieldname)

    return filterpos, filterneg, fieldname


def input_hu_filter(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    hu_layer: QgsVectorLayer,
    filter_file: str,
    min_area: float = 56.8,
    cell_size: int = 50,
    neighborhood_radius: int = 100,
    debug_mode: bool = False,
    workspace_path: str = None,
) -> QgsVectorLayer:
    """Filter building footprints by function type and density-based residential zones.

    Steps:

    1. Select residential buildings (positive filter list) and derive a
       density-based selection polygon from their centroids.
    2. Exclude non-residential buildings (negative filter list) that fall
       within the residential zone.
    3. Remove dissolved building groups and individual buildings below
       the area threshold.

    Args:
        hu_layer: Input building footprint polygon layer.
        filter_file: Path to the filter definition text file.
        min_area: Minimum combined area threshold for dissolved building groups.
            Processing is skipped when the layer has fewer features than this
            value. Defaults to 56.8.
        cell_size: Cell size in meters for the kernel density raster. Defaults to 50.
        neighborhood_radius: Search radius in meters for the kernel density
            estimation. Defaults to 100.
        debug_mode: If True, saves intermediate layers as GeoPackages for
            visual step-by-step inspection. Defaults to False.
        workspace_path: Base workspace path for debug output. Required when
            ``debug_mode`` is True.

    Returns:
        Filtered building footprint layer as a dissolved QgsVectorLayer.
    """
    if not hu_layer.isValid() or hu_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise RuntimeError("hu_layer must be a valid polygon layer.")

    building_count = hu_layer.featureCount()

    if building_count > min_area:

        hu_layer = shp_area(hu_layer)
        filterpos, filterneg, _ = import_filter(filter_file, hu_layer)

        # Step 1: Select residential buildings (positive filter)
        residential_layer = processing.run("native:extractbyexpression", {
            'INPUT': hu_layer,
            'EXPRESSION': filterpos,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(residential_layer, QgsVectorLayer):
            raise RuntimeError("Failed to create residential_layer")
        if debug_mode and workspace_path:
            save_debug_layer(residential_layer, _DEBUG_TOOL_NAME, "after_positive_filter", workspace_path)

        # Feature-to-Point
        res_cent = processing.run("native:centroids", {
            'INPUT': residential_layer,
            'ALL_PARTS': False,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(res_cent, QgsVectorLayer):
            raise RuntimeError("Failed to create res_cent")
        if debug_mode and workspace_path:
            save_debug_layer(res_cent, _DEBUG_TOOL_NAME, "after_centroids", workspace_path)

        if res_cent.featureCount() == 0:
            Logger.log(
                "Kein Gebäude nach positivem Filter übrig – Filterung wird übersprungen.",
                level="WARNING",
            )
            return hu_layer

        # Create point density
        hu_raster = QgsProcessingUtils.generateTempFilename("hu_raster.tif")
        processing.run("qgis:heatmapkerneldensityestimation", {
            'INPUT': res_cent,
            'RADIUS': neighborhood_radius,
            'PIXEL_SIZE': cell_size,
            'DECAY': 0,
            'OUTPUT': hu_raster
        })

        # Raster-to-Point
        res_density_points = processing.run("native:pixelstopoints", {
            'INPUT_RASTER': hu_raster,
            'RASTER_BAND': 1,
            'FIELD_NAME': 'VALUE',
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(res_density_points, QgsVectorLayer):
            raise RuntimeError("Failed to create res_density_points")

        # Filter points by density value
        filtered_points = processing.run("native:extractbyexpression", {
            'INPUT': res_density_points,
            'EXPRESSION': f"value >= {_MIN_DENSITY_VALUE}",
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(filtered_points, QgsVectorLayer):
            raise RuntimeError("Failed to create filtered_points")
        if debug_mode and workspace_path:
            save_debug_layer(filtered_points, _DEBUG_TOOL_NAME, "after_density_filter", workspace_path)

        # Buffer around filtered points
        points_buffer = processing.run("native:buffer", {
            'INPUT': filtered_points,
            'DISTANCE': cell_size / _BUFFER_CELL_DIVISOR,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 1,
            'DISSOLVE': True,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(points_buffer, QgsVectorLayer):
            raise RuntimeError("Failed to create points_buffer")
        if debug_mode and workspace_path:
            save_debug_layer(points_buffer, _DEBUG_TOOL_NAME, "after_density_buffer", workspace_path)

        # Step 2: Exclude buildings (negative filter)
        negative_layer = processing.run("native:extractbyexpression", {
            'INPUT': hu_layer,
            'EXPRESSION': filterneg,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(negative_layer, QgsVectorLayer):
            raise RuntimeError("Failed to create negative_layer")
        if debug_mode and workspace_path:
            save_debug_layer(negative_layer, _DEBUG_TOOL_NAME, "after_negative_filter", workspace_path)

        # Exclude negative buildings within residential area
        hu_neg_sel = select_and_save_by_location(negative_layer, points_buffer, predicate=2)
        hu_final = select_and_save_by_location(hu_layer, hu_neg_sel, predicate=2)
        if debug_mode and workspace_path:
            save_debug_layer(hu_final, _DEBUG_TOOL_NAME, "after_neg_exclusion", workspace_path)

        # Step 3: Delete small buildings
        hu_diss = processing.run("native:dissolve", {
            'INPUT': hu_final,
            'FIELD': [],
            'SEPARATE_DISJOINT': True,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        shp_area2(hu_diss, "Area")
        if debug_mode and workspace_path:
            save_debug_layer(hu_diss, _DEBUG_TOOL_NAME, "after_dissolve", workspace_path)

        diss_del = processing.run("native:extractbyattribute", {
            'INPUT': hu_diss,
            'FIELD': 'Area',
            'OPERATOR': 2,
            'VALUE': min_area,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if not isinstance(diss_del, QgsVectorLayer):
            raise RuntimeError("Failed to create final_layer")
        if debug_mode and workspace_path:
            save_debug_layer(diss_del, _DEBUG_TOOL_NAME, "after_group_filter", workspace_path)

        hu_final_sel = select_and_save_by_location(hu_final, diss_del, predicate=0)
        shp_area2(hu_final_sel, "Area")

        final_layer = processing.run("native:extractbyattribute", {
            'INPUT': hu_final_sel,
            'FIELD': 'Area',
            'OPERATOR': 2,
            'VALUE': _MIN_BUILDING_AREA,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(final_layer, _DEBUG_TOOL_NAME, "after_area_filter", workspace_path)

        final_layer_diss = processing.run("native:dissolve", {
            'INPUT': final_layer,
            'FIELD': [],
            'SEPARATE_DISJOINT': True,
            'OUTPUT': 'memory:'
        })['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(final_layer_diss, _DEBUG_TOOL_NAME, "after_final_dissolve", workspace_path)

        return final_layer_diss

    Logger.log(
        f"Anzahl der Gebäude für Filterung zu gering: {building_count}",
        level="WARNING",
    )
    return hu_layer
