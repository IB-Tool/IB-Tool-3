# -*- coding: utf-8 -*-
"""Snap grouped building polygons to the road network.

For each building group, orthogonal projection lines are drawn from the building
outline to the adjacent road segments. The combined line geometry is polygonized
and the result is clipped to the relevant city block, producing road-aligned
settlement boundaries.

Private helpers and algorithm constants live in helpers/edge_catch_utils.py.

Public API
----------
edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs, workspace_path,
           debug_mode)
"""
from qgis.core import QgsProcessing
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.geometry_utils import shp_area2, create_empty_layer
from ..helpers.debug_utils import save_debug_layer
from ..helpers.edge_catch_utils import (
    filter_roads_near_buildings,
    process_single_feature,
    ROAD_SEGMENT_LENGTH,
    ROAD_BUFFER_DISTANCE,
)


# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "05_EdgeCatch"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs, workspace_path,
               debug_mode=False):
    """Snap grouped building polygons to the road network.

    Pre-filters the road network to segments adjacent to buildings, then
    processes each building group individually via ``process_single_feature``.
    Results are accumulated into a single output layer.

    Debug checkpoints (when ``debug_mode`` is active):

    - ``road_segs_near_buildings`` — road segments adjacent to buildings,
      used as input to the main loop (saved inside ``filter_roads_near_buildings``)
    - ``polygons_merged`` — final accumulated output layer

    Args:
        grouped_bdgs: QgsVectorLayer - grouped building polygon layer.
        hu_input: QgsVectorLayer - individual building footprints used for road
            pre-filtering.
        road_network: QgsVectorLayer - road line layer.
        bloecke: QgsVectorLayer - city block polygon layer.
        crs: QgsCoordinateReferenceSystem - coordinate reference system.
        workspace_path: str - path to the workspace directory.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.

    Returns:
        QgsVectorLayer - processed polygon layer with road-snapped building groups.
    """
    # Pre-processing: reduce road network to segments adjacent to buildings
    road_network = filter_roads_near_buildings(
        road_network, hu_input, ROAD_SEGMENT_LENGTH, ROAD_BUFFER_DISTANCE,
        debug_mode=debug_mode, workspace_path=workspace_path
    )
    Logger.log(
        f"Straßennetz auf {road_network.featureCount()} gebäudenahe Segmente reduziert",
        level="INFO"
    )
    if road_network.featureCount() == 0:
        Logger.log(
            "Kein Straßensegment grenzt an Gebäude – EdgeCatch wird übersprungen",
            level="WARNING"
        )
        return grouped_bdgs

    merge_layer = create_empty_layer("merge_layer_edge_catch", "Polygon", crs.authid())
    polygons_merge = None

    shp_area2(grouped_bdgs)
    for feature in grouped_bdgs.getFeatures():
        result = process_single_feature(
            feature, road_network, bloecke, crs,
            debug_mode=debug_mode, workspace_path=workspace_path
        )
        if result is None:
            continue

        try:
            polygons_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [result, merge_layer],
                'CRS': crs,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            merge_layer = polygons_merge
        except Exception as e:
            Logger.log(f"Group could not be merged - {str(e)}", level="CRITICAL")
            continue

    if not polygons_merge:
        Logger.log("No valid polygons produced in edge_catch", level="WARNING")
        polygons_merge = grouped_bdgs

    if debug_mode and workspace_path:
        save_debug_layer(polygons_merge, _DEBUG_TOOL_NAME, "polygons_merged", workspace_path)

    return polygons_merge
