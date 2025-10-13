import math
from operator import itemgetter

from qgis.core import (
    QgsFeature,
    QgsVectorLayer,
    QgsGeometry,
    QgsPoint,
    QgsProcessing,
    edit,
)
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.geometry_utils import shp_area2, create_empty_layer
from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.edge_catch_utils import (create_shortest_lines_to_roads,
                                        filter_ortho_lines,
                                        delete_first_point)


def edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs, workspace_path):
    """
    Verarbeitet Gebäudegeometrien (grouped_bdgs) und schnappt diese an Straßen an,
    füllt Lücken und schließt Polygone räumlich an Straßen an.

    :param grouped_bdgs: Eingangs-Polygon-Layer der zusammengefassten Gebäude
    :param hu_input: Gebäudeumrisse als Layer (HU Input)
    :param road_network: Straßen-Layer (Line-Layer)
    :param bloecke: Straßenblöcke-Layer
    :param crs: Koordinatensystem des Layers
    :return: Verarbeiteter Polygon-Layer
    """

    # Constants
    DISTANCE_THRESHOLD = 70 #
    ANGLE_THRESHOLD = 2  # Define the tolerance for grouping lines based on angle similarity

    def group_lines_by_angle(lines):
        """
        Groups lines with similar angles into distinct groups.
        """
        lines= sorted(lines, key=itemgetter(-2))
        groups = [[lines[0]]]  # Initialize with the first line
        for line in lines:
            # Check angle difference with the last item in the latest group
            if abs(line[-2] - groups[-1][-1][-2]) <= ANGLE_THRESHOLD:
                groups[-1].append(line)
            else:
                groups.append([line])  # Start a new group for this line
        return groups


    def calculate_average_distances(building_groups):
        """Calculate the average distance for each group."""
        avg_distances = []
        for group in building_groups:
            total_distance = sum(b[3] for b in group)
            count = len(group)
            avg_distances.append(total_distance / count)
        return avg_distances



    merge_layer = create_empty_layer("merge_layer_edge_catch", "Polygon", crs.authid())

    shp_area2(grouped_bdgs)
    for feature in grouped_bdgs.getFeatures():

        fid = feature.id()


        shapeareagroup = feature['Area']
        single_feature = QgsFeature(feature)
    
        # Neues temporäres Layer erstellen
        temporary_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", f"temp_feature_{fid}", "memory")
        provider = temporary_layer.dataProvider()
    
        # Füge das Feature zum temporären Layer hinzu
        provider.addFeatures([single_feature])

        #outline_points_list = []
        outline_points = processing.run(
            "native:extractvertices",
            {
                'INPUT': temporary_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
        )['OUTPUT']
        #outline_points_list.append(outline_points)


        outline_points = delete_first_point(outline_points)
        save_temp_layer_to_gpkg(outline_points, f"M_Sel_HU_Vertics_{fid}", workspace_path)


        block_sel = processing.run("native:extractbylocation", {
            'INPUT': bloecke,
            'PREDICATE': [0],  # Intersects
            'INTERSECT': outline_points,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        save_temp_layer_to_gpkg(block_sel, f"M_blocksel_{fid}",
                                workspace_path)

        road_network_sel = processing.run("native:extractbylocation", {
            'INPUT': road_network,
            'PREDICATE': [0],  # Intersects
            'INTERSECT': block_sel,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        save_temp_layer_to_gpkg(road_network_sel, f"M_roadsel_{fid}",
                                workspace_path)

        hu_ortho = create_shortest_lines_to_roads(outline_points, road_network_sel)

        save_temp_layer_to_gpkg(hu_ortho, f"M_hu_ortho_{fid}",
                                workspace_path)

        hu_ortho_filter = filter_ortho_lines(hu_ortho)
        save_temp_layer_to_gpkg(hu_ortho_filter, f"M_hu_ortho_filter_{fid}",
                                workspace_path)

        #save_temp_layer_to_gpkg(hu_ortho_ext, f"N_lines_ext_{fid}", workspace_path)

        group_outline = processing.run("native:polygonstolines", {
            'INPUT': temporary_layer,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        # Trenne das Linienfeature an den Stützpunkten
        group_outline_split = processing.run("native:explodelines", {
            'INPUT': group_outline,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_merge = processing.run("native:mergevectorlayers", {
            'LAYERS': [road_network_sel, hu_ortho_filter, group_outline_split],
            'CRS': crs,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_merge_ext = processing.run("native:extendlines", {
            'INPUT': lines_merge,
            'START_DISTANCE': 1, 'END_DISTANCE': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        save_temp_layer_to_gpkg(lines_merge_ext, f"N_lines_merge_{fid}",
                               workspace_path)

        # Vor der Polygonisierung die Geometrien reparieren
        lines_merge_ext_fixed = processing.run("native:fixgeometries", {
            'INPUT': lines_merge_ext,
            'METHOD': 1,  # Structure method
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        lines_polygons = processing.run("native:polygonize", {
            'INPUT': lines_merge_ext_fixed,
            'KEEP_FIELDS': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']


        save_temp_layer_to_gpkg(lines_polygons, f"N_lines_polygons_{fid}", workspace_path)
        
        lines_polygons_hu = processing.run("native:extractbylocation",
                                           {'INPUT': lines_polygons,
                                            'PREDICATE': [0],
                                            'INTERSECT': temporary_layer,
                                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                           })['OUTPUT']


        lines_polygons_block = processing.run("native:intersection",
                       {'INPUT': lines_polygons_hu,
                        'OVERLAY': block_sel,
                        'INPUT_FIELDS': [],
                        'OVERLAY_FIELDS': [],
                        'OVERLAY_FIELDS_PREFIX': '',
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                        'GRID_SIZE': None
                        })['OUTPUT']

        save_temp_layer_to_gpkg(lines_polygons_block, f"N_lines_polygons_block_{fid}",
                                workspace_path)


        lines_polygons_block_fix = processing.run("native:fixgeometries",
                       {'INPUT': lines_polygons_block,
                        'METHOD': 1,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']

        shp_area2(lines_polygons_block_fix)

        lines_polygons_block_small = processing.run("native:extractbyexpression",
                                                {'INPUT': lines_polygons_block_fix,
                                                 'EXPRESSION': '"Area" < {}'.format((str(shapeareagroup * 2))), #TODO Operator prüfen ob > oder <
                                                 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                                 })['OUTPUT']

        #lines_polygons_block_small = lines_polygons_hu
        #save_temp_layer_to_gpkg(lines_polygons_block_small, f"lines_polygons_block_small_{feature.id()}")

        #TODO Merge in der Art ist rechenintensiv
        try:
            polygones_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [lines_polygons_block_small, merge_layer],
                'CRS': crs,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
            merge_layer = polygones_merge
        except Exception as e:
            Logger.log(f"Group could not be merged - {str(e)}", level="CRITICAL")
            continue


    # Rückgabe als Fallback
    if not polygones_merge:
        Logger.log("No valid rect_merge produced in mst_clustering", level="WARNING")
        polygones_merge = grouped_bdgs

    return polygones_merge

