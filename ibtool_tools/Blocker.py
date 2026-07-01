# -*- coding: utf-8 -*-
"""Create city block polygons from a road network and partition boundary.

Polygonizes the merged road network and partition outline, removes blocks
that contain no building footprints, and annotates each remaining block
with a unique NAME attribute.

Public API
----------
blocker(road_network, hu_input, partition, debug_mode, workspace_path)
"""

from qgis.core import (
    QgsField,
    QgsProcessing,
)
from qgis.PyQt.QtCore import QMetaType

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "01_Blocker"

# ---------------------------------------------------------------------------
# QGIS predicate / method codes (used in native:selectbylocation)
# ---------------------------------------------------------------------------
_PREDICATE_CONTAINS = 0    # keep blocks that contain at least one building
_SELECTION_METHOD_NEW = 0  # replace any previous selection with a fresh one


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_block_polygons(road_network, partition, debug_mode=False, workspace_path=None):
    """Polygonize the merged road network and partition outline.

    Clips *road_network* to *partition*, merges the clipped roads with the
    partition outline, and polygonizes the result to produce raw block polygons
    (some may contain no buildings and will be filtered afterwards).

    Debug checkpoints (when ``debug_mode`` is active):

    - ``roads_in_partition`` — clipped road segments inside the partition
    - ``blocks_raw`` — all polygonized blocks before the building filter

    Args:
        road_network: Road network polyline layer for the study area.
        partition: Polygon layer defining the current study area partition.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        A QgsVectorLayer of raw polygonized block features.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    partition_outline = safe_processing_run("native:polygonstolines", {
        'INPUT': partition,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    roads_in_partition = safe_processing_run("native:intersection", {
        'INPUT': road_network,
        'OVERLAY': partition,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(roads_in_partition, _DEBUG_TOOL_NAME, "roads_in_partition", workspace_path)

    lines_merged = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [partition_outline, roads_in_partition],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    blocks_layer = safe_processing_run("native:polygonize", {
        'INPUT': lines_merged,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(blocks_layer, _DEBUG_TOOL_NAME, "blocks_raw", workspace_path)

    return blocks_layer


def _remove_blocks_without_buildings(blocks_layer, hu_input, debug_mode=False, workspace_path=None):
    """Delete block features that contain no buildings (in place).

    Selects blocks that spatially contain at least one building centroid and
    removes all others from *blocks_layer*.

    Debug checkpoint (when ``debug_mode`` is active):

    - ``blocks_with_buildings`` — blocks remaining after the spatial filter

    Args:
        blocks_layer: Mutable block polygon layer to filter.
        hu_input: Building footprint layer used as the spatial filter reference.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=_DEBUG_TOOL_NAME)

    safe_processing_run("native:selectbylocation", {
        'INPUT': blocks_layer,
        'PREDICATE': [_PREDICATE_CONTAINS],
        'INTERSECT': hu_input,
        'METHOD': _SELECTION_METHOD_NEW,
    }, **_dbg)

    selected_ids = set(blocks_layer.selectedFeatureIds())
    blocks_layer.startEditing()
    for feature in blocks_layer.getFeatures():
        if feature.id() not in selected_ids:
            blocks_layer.deleteFeature(feature.id())
    blocks_layer.commitChanges()

    if debug_mode and workspace_path:
        save_debug_layer(blocks_layer, _DEBUG_TOOL_NAME, "blocks_with_buildings", workspace_path)


def _assign_block_names(blocks_layer):
    """Add a ``NAME`` field and populate it with ``Block_<id>`` values (in place).

    Creates the ``NAME`` field if it does not already exist, then writes a
    unique identifier string to every feature in *blocks_layer*.

    Args:
        blocks_layer: Mutable block polygon layer to annotate.
    """
    blocks_layer.startEditing()
    if blocks_layer.dataProvider().fieldNameIndex("NAME") < 0:
        blocks_layer.dataProvider().addAttributes([
            QgsField("NAME", QMetaType.QString)
        ])
        blocks_layer.updateFields()

    for feature in blocks_layer.getFeatures():
        feature["NAME"] = f"Block_{feature.id()}"
        blocks_layer.updateFeature(feature)
    blocks_layer.commitChanges()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def blocker(road_network, hu_input, partition, debug_mode=False, workspace_path=None):
    """Create city blocks from a road network and partition boundary.

    Polygonizes the merged road network and partition outline, removes blocks
    that contain no building footprints, and annotates each remaining block
    with a unique ``NAME`` attribute.

    Debug checkpoints written to ``workspace/debug/Blocker/``:

    1. ``roads_in_partition`` — road segments clipped to the partition
    2. ``blocks_raw`` — all polygonized blocks before filtering
    3. ``blocks_with_buildings`` — blocks that contain at least one building

    Args:
        road_network: Road network polyline layer for the study area.
        hu_input: Building footprint polygon layer used to filter empty blocks.
        partition: Polygon layer defining the current study area partition.
        debug_mode: If True, saves intermediate results as numbered GeoPackages
            under ``workspace/debug/Blocker/``. Defaults to False.
        workspace_path: Base path for debug output files. Required when
            ``debug_mode`` is True. Defaults to None.

    Returns:
        A QgsVectorLayer of named city block polygons, one per enclosed area
        that contains at least one building.
    """
    blocks_layer = _build_block_polygons(road_network, partition, debug_mode, workspace_path)
    _remove_blocks_without_buildings(blocks_layer, hu_input, debug_mode, workspace_path)
    _assign_block_names(blocks_layer)

    Logger.log("Blocker End - blocks", "SUCCESS")
    return blocks_layer
