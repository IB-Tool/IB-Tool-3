from PyQt5.QtCore import QVariant
from qgis._core import QgsCoordinateReferenceSystem
from qgis.core import (
    QgsProcessingFeatureSourceDefinition,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsGeometry,
    QgsPoint,
    QgsExpression,
    QgsFeatureRequest,
    QgsVectorFileWriter,
    QgsProcessing,
    edit
)

from qgis._analysis import QgsNativeAlgorithms

from operator import itemgetter
from qgis import processing
import math

from ..helpers.logger import Logger
from ..helpers.geometry_utils import shp_area2, create_empty_layer

def edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs):
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


    outline_points_list = []
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

        outline_points = processing.run(
            "native:extractvertices",
            {
                'INPUT': temporary_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
        )['OUTPUT']
        outline_points_list.append(outline_points)

        block_sel = processing.run("native:extractbylocation", {
            'INPUT': bloecke,
            'PREDICATE': [0],  # Intersects
            'INTERSECT': outline_points,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        road_network_sel = processing.run("native:extractbylocation", {
            'INPUT': road_network,
            'PREDICATE': [0],  # Intersects
            'INTERSECT': block_sel,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        road_network_sel_dense = processing.run("native:densifygeometriesgivenaninterval",
                       {'INPUT': road_network_sel,
                        'INTERVAL': 3,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']

        road_network_sel_dense_vert = processing.run("native:extractvertices", {
                        'INPUT': road_network_sel_dense,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']

        # Removing features from outline_points where the 'distance' field is 0
        with edit(outline_points):
            for feature2 in outline_points.getFeatures():
                if 'distance' in feature2.fields().names() and feature2['distance'] == 0:
                    outline_points.deleteFeature(feature2.id())

        distance_matrix = processing.run("qgis:distancematrix",
                       {'INPUT': outline_points,
                        'INPUT_FIELD': 'vertex_index',
                        'TARGET': road_network_sel_dense_vert,
                        'TARGET_FIELD': 'OBJART',
                        'MATRIX_TYPE': 0,
                        'NEAREST_POINTS': 1,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                        })['OUTPUT']

        distance_matrix_singlepart = processing.run("native:multiparttosingleparts", {
            'INPUT': distance_matrix,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

        distance_matrix_singlepart_xy = processing.run("native:addxyfields", {
            'INPUT': distance_matrix_singlepart,
            'CRS': crs,
            'PREFIX': '',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

        groups = []
        grouped_lines = []


        id2, x2, y2 = None, None, None


        for feature3 in distance_matrix_singlepart_xy.getFeatures():
            id1 = feature3['InputID']
            distance = feature3['distance']
            x1 = feature3['x']
            y1 = feature3['y']

            if id1 == id2:
                angle = math.atan2(y2 - y1, x2 - x1)
                if distance < DISTANCE_THRESHOLD:
                    grouped_lines.append([x1, y1, x2, y2, angle, distance])

            else:
                id2 = id1
                x2 = x1
                y2 = y1

        # Creating an array of point pairs that describe the edges of the rectangle

        outline_points_xy = processing.run("native:addxyfields", {
            'INPUT': outline_points,
            'CRS': crs,
            'PREFIX': '',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        corner_points = []
        for feature4 in outline_points_xy.getFeatures():
            x1 = feature4['x']
            y1 = feature4['y']
            corner_points.append([x1, y1])


        rect_edges = []
        for i in range(len(corner_points)):
            # Connect each corner to the next, and the last corner back to the first
            start_point = corner_points[i]
            end_point = corner_points[(i + 1) % len(corner_points)]
            rect_edges.append([start_point, end_point])

        ArrayOfLines = []

        if len(grouped_lines) > 1:
            grouped_angel = group_lines_by_angle(grouped_lines)

            if len(grouped_angel) > 2:
                avg_distances = calculate_average_distances(grouped_angel)

                # Identify the group with the maximum average distance
                current_max, prev_max = 0, 0
                max_index = -1
                for idx, avg_distance in enumerate(avg_distances):
                    if avg_distance > current_max:
                        prev_max, current_max = current_max, avg_distance
                        max_index = idx

                # Remove the group if its distance is significantly higher
                if current_max > 1.5 * prev_max:
                    grouped_angel.pop(max_index)

            try:
                for group_of_lines in grouped_angel:
                    for line in group_of_lines:
                        ArrayOfLines.append([[line[0], line[1]], [line[2], line[3]]]) #x1.coordinate, y1.coordinate, x2.coordinate, y2.coordinate

            except:
                for group_of_lines in grouped_angel:
                    for k in group_of_lines:
                        for line in k:
                            ArrayOfLines.append([[line[0], line[1]], [line[2], line[3]]])


            for line in rect_edges:
                ArrayOfLines.append(line)


            # Erstelle ein neues temporäres Polyline-Layer
            polyline_layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", "polyline_layer",
                                            "memory")
            provider = polyline_layer.dataProvider()

            # Füge die Linien aus dem ArrayOfLines hinzu
            for group_of_lines in ArrayOfLines:
                points = [QgsPoint(group_of_lines[0][0], group_of_lines[0][1]), QgsPoint(group_of_lines[1][0], group_of_lines[1][1])]
                polyline_feature = QgsFeature()
                polyline_feature.setGeometry(QgsGeometry.fromPolyline(points))
                provider.addFeature(polyline_feature)

            if not polyline_layer.isValid():
               Logger.log(f"Layer '{polyline_layer.name()}' ist ungültig.", level="INFO")

            if not road_network_sel.isValid():
                Logger.log(f"Layer '{road_network_sel.name()}' ist ungültig.", level="INFO")

            #save_temp_layer_to_gpkg(polyline_layer, f"polyline_layer_{feature.id()}")
            #save_temp_layer_to_gpkg(road_network_sel_dense, f"road_network_sel_dense_{feature.id()}")

            try:
                polyline_layer_snap1 = processing.run("native:snapgeometries",
                               {'INPUT': polyline_layer,
                                'REFERENCE_LAYER': outline_points_xy,
                                'TOLERANCE': 1,
                                'BEHAVIOR': 0,
                                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                })['OUTPUT']


                polyline_layer_snap2 = processing.run("native:snapgeometries",
                               {'INPUT': polyline_layer_snap1,
                                'REFERENCE_LAYER': road_network_sel_dense,
                                'TOLERANCE': 1,
                                'BEHAVIOR': 0,
                                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                })['OUTPUT']
            except:
                Logger.log("EdgeCatch abgebrochen für Feature {}.".format(feature.id()), level="WARNING")
                continue
                #TODO interne Fehlerbehandlung aktivieren: ungültige Geometrien ignorieren

            road_network_sel_sel = processing.run("native:extractbylocation",
                           {'INPUT': road_network_sel_dense,
                            'PREDICATE': [0, 4, 7],
                            'INTERSECT': polyline_layer_snap2,
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                            })['OUTPUT']

            lines_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [road_network_sel_dense, polyline_layer_snap2],
                'CRS': crs,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            lines_polygons = processing.run("native:polygonize", {
                'INPUT': lines_merge,
                'KEEP_FIELDS': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })['OUTPUT']


            '''
            
            lines_polygons_hu = processing.run("native:extractbylocation",
                                               {'INPUT': lines_polygons,
                                                'PREDICATE': [0],
                                                'INTERSECT': hu_input,
                                                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                               })['OUTPUT']
            '''
            #TODO Prüfen, ob das Sinn macht

            lines_polygons_block = processing.run("native:intersection",
                           {'INPUT': lines_polygons,
                            'OVERLAY': block_sel,
                            'INPUT_FIELDS': [],
                            'OVERLAY_FIELDS': [],
                            'OVERLAY_FIELDS_PREFIX': '',
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
                            'GRID_SIZE': None
                            })['OUTPUT']

            lines_polygons_block_fix = processing.run("native:fixgeometries",
                           {'INPUT': lines_polygons_block,
                            'METHOD': 1,
                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                            })['OUTPUT']

            shp_area2(lines_polygons_block_fix)

            lines_polygons_block_small = processing.run("native:extractbyexpression",
                                                    {'INPUT': lines_polygons_block_fix,
                                                     'EXPRESSION': '"Area" < {}'.format((str(shapeareagroup * 3))), #TODO Operator prüfen ob > oder <
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
        else:
            continue

    # Rückgabe als Fallback
    if not polygones_merge:
        Logger.log("No valid rect_merge produced in mst_clustering", level="WARNING")
        polygones_merge = grouped_bdgs

    return polygones_merge

