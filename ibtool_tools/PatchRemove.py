# -*- coding: utf-8 -*-
"""Remove settlement patches that are too small or contain too few buildings.

Converts multipart input to singlepart, counts intersecting buildings per
patch, and filters out patches below configurable size and building-count
thresholds. Dense blocks identified by identify_dense_blocks are always
retained regardless of patch size.

Public API
----------
patch_remove(input_poly, input_bdg, crs, workspace_path, min_patch_size,
             min_bdg_count, footprint_area_sum, footprint_density_threshold,
             debug_mode)
"""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsField,
    QgsProcessing,
    QgsVectorLayer,
    edit,
)
from qgis.PyQt.QtCore import QMetaType
from qgis import processing

from .FootprintDensity import identify_dense_blocks
from ..helpers.geometry_utils import shp_area2
from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "08_PatchRemove"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_PATCH_SIZE = 10_000
"""Minimum patch area (m²) below which a settlement polygon is discarded."""

DEFAULT_MIN_BDG_COUNT = 20
"""Minimum number of buildings a patch must contain to be retained."""

DEFAULT_FOOTPRINT_AREA_SUM = 6_000
"""Minimum total footprint area (m²) for a dense block to be retained unconditionally."""

DEFAULT_FOOTPRINT_DENSITY_THRESHOLD = 18
"""Footprint density threshold (%) passed to identify_dense_blocks."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def patch_remove(
    input_poly: QgsVectorLayer,
    input_bdg: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    workspace_path: str,
    min_patch_size: int = DEFAULT_MIN_PATCH_SIZE,
    min_bdg_count: int = DEFAULT_MIN_BDG_COUNT,
    footprint_area_sum: int = DEFAULT_FOOTPRINT_AREA_SUM,
    footprint_density_threshold: int = DEFAULT_FOOTPRINT_DENSITY_THRESHOLD,
    debug_mode: bool = False,
) -> QgsVectorLayer:
    """Remove settlement patches that are too small or contain too few buildings.

    Converts the input polygon layer to single parts, counts intersecting
    buildings per patch, and filters out patches below the size and building
    count thresholds. Dense blocks identified by ``identify_dense_blocks``
    are merged back in so that high-density areas are always retained.

    Args:
        input_poly: Input settlement polygon layer (may contain multipart features).
        input_bdg: Building footprint layer used for intersection counting.
        crs: Coordinate reference system applied to the merged output layer.
        workspace_path: Path to the project workspace used for debug output.
        debug_mode: If True, saves intermediate layers as GeoPackages for
            visual step-by-step inspection. Defaults to False.
        min_patch_size: Minimum patch area in square metres. Defaults to 10000.
        min_bdg_count: Minimum number of buildings a patch must contain.
            Defaults to 20.
        footprint_area_sum: Minimum total footprint area (sqm) for dense blocks
            to be retained. Defaults to 6000.
        footprint_density_threshold: Density threshold passed to
            ``identify_dense_blocks``. Defaults to 18.

    Returns:
        Merged polygon layer containing patches that passed the size/count
        filter and all dense blocks above the footprint area threshold.
    """
    # Split multipart features into single parts
    poly_single_parts = processing.run("native:multiparttosingleparts", {
        'INPUT': input_poly,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(poly_single_parts, _DEBUG_TOOL_NAME, "after_single_parts", workspace_path)

    # Add a unique block name field
    poly_single_parts.dataProvider().addAttributes([QgsField("NAME", QMetaType.QString)])
    poly_single_parts.updateFields()

    with edit(poly_single_parts):
        for feature in poly_single_parts.getFeatures():
            feature['NAME'] = f'Block_{feature.id()}'
            poly_single_parts.updateFeature(feature)

    # Add a field to store the intersecting building count
    poly_single_parts.dataProvider().addAttributes([QgsField("join_count", QMetaType.Int)])
    poly_single_parts.updateFields()

    with edit(poly_single_parts):
        for feature in poly_single_parts.getFeatures():
            name = feature['NAME']
            block_sel = processing.run("native:extractbyattribute", {
                'INPUT': poly_single_parts,
                'FIELD': 'NAME',
                'OPERATOR': 0,
                'VALUE': name,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            })['OUTPUT']

            try:
                intersect = processing.run("native:extractbylocation", {
                    'INPUT': input_bdg,
                    'PREDICATE': [0],
                    'INTERSECT': block_sel,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                })['OUTPUT']

                join_count = intersect.featureCount()
                feature['join_count'] = join_count
                poly_single_parts.updateFeature(feature)
            except Exception as e:
                Logger.log(
                    f"Fehler bei der Verarbeitung von Feature {feature.id()}: {e}",
                    level="WARNING",
                )

    shp_area2(poly_single_parts)
    if debug_mode and workspace_path:
        save_debug_layer(poly_single_parts, _DEBUG_TOOL_NAME, "after_building_count", workspace_path)

    # Keep only patches above the size and building-count thresholds
    area_expression = f'"Area" > {min_patch_size} and "join_count" > {min_bdg_count}'
    poly_single_parts_sel = processing.run("native:extractbyexpression", {
        'INPUT': poly_single_parts,
        'EXPRESSION': area_expression,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(poly_single_parts_sel, _DEBUG_TOOL_NAME, "after_patch_filter", workspace_path)

    # Identify and filter dense blocks by footprint area
    dense_blocks = identify_dense_blocks(input_bdg, poly_single_parts, footprint_density_threshold)
    if debug_mode and workspace_path:
        save_debug_layer(dense_blocks, _DEBUG_TOOL_NAME, "after_dense_blocks", workspace_path)

    dense_expression = (
        f'"SHAPE_AREA" >= {min_patch_size} or "FOOTPRINT_AREA_sum" >= {footprint_area_sum}'
    )
    dense_blocks_sel = processing.run("native:extractbyexpression", {
        'INPUT': dense_blocks,
        'EXPRESSION': dense_expression,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(dense_blocks_sel, _DEBUG_TOOL_NAME, "after_dense_filter", workspace_path)

    # Merge filtered patches with dense blocks
    merge = processing.run("native:mergevectorlayers", {
        'LAYERS': [dense_blocks_sel, poly_single_parts_sel],
        'CRS': crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(merge, _DEBUG_TOOL_NAME, "after_merge", workspace_path)

    return merge
