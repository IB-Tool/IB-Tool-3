import math
from operator import itemgetter
from collections import defaultdict

from qgis.core import (
    QgsFeature,
    QgsVectorLayer,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProcessing,
    QgsField,
    edit,
)
from qgis.PyQt.QtCore import QVariant
from qgis import processing

from ..helpers.logger import Logger
from ..helpers.geometry_utils import shp_area2, create_empty_layer
from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.edge_catch_utils import (create_shortest_lines_to_roads,
                                        filter_ortho_lines,
                                        delete_first_point)


def _normalize_node(point):
    """Create a hashable node key with limited precision."""
    return (round(point.x(), 8), round(point.y(), 8))


def _build_minimized_lines_from_selection(road_network_sel, crs):
    """
    Reduces a selected road network to a minimum number of line features.

    The method extracts all segment end/support vertices, removes duplicate segments,
    and rebuilds the network as chains between intersections/endpoints.
    """
    if road_network_sel.featureCount() == 0:
        return road_network_sel

    unique_segments = {}
    adjacency = defaultdict(set)

    for feature in road_network_sel.getFeatures():
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue

        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
        else:
            parts = [geometry.asPolyline()]

        for part in parts:
            if len(part) < 2:
                continue
            for start, end in zip(part[:-1], part[1:]):
                start_key = _normalize_node(start)
                end_key = _normalize_node(end)
                if start_key == end_key:
                    continue

                segment_key = tuple(sorted([start_key, end_key]))
                if segment_key in unique_segments:
                    continue

                unique_segments[segment_key] = (start_key, end_key)
                adjacency[start_key].add(end_key)
                adjacency[end_key].add(start_key)

    if not unique_segments:
        return road_network_sel

    visited_segments = set()
    result_layer = QgsVectorLayer(f"LineString?crs={crs.authid()}", "road_network_reduced", "memory")
    result_provider = result_layer.dataProvider()
    result_provider.addAttributes([QgsField("src_count", QVariant.Int)])
    result_layer.updateFields()

    def traverse_chain(start_node, next_node):
        chain = [start_node, next_node]
        prev_node = start_node
        curr_node = next_node

        while len(adjacency[curr_node]) == 2:
            candidates = [node for node in adjacency[curr_node] if node != prev_node]
            if not candidates:
                break
            forward_node = candidates[0]
            segment = tuple(sorted([curr_node, forward_node]))
            if segment in visited_segments:
                break
            chain.append(forward_node)
            prev_node = curr_node
            curr_node = forward_node

        return chain

    start_nodes = [node for node, neighbors in adjacency.items() if len(neighbors) != 2]
    if not start_nodes:
        start_nodes = [next(iter(adjacency.keys()))]

    features_to_add = []
    for start_node in start_nodes:
        for neighbor in adjacency[start_node]:
            segment = tuple(sorted([start_node, neighbor]))
            if segment in visited_segments:
                continue

            chain = traverse_chain(start_node, neighbor)
            for a, b in zip(chain[:-1], chain[1:]):
                visited_segments.add(tuple(sorted([a, b])))

            new_feature = QgsFeature(result_layer.fields())
            new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
            new_feature["src_count"] = len(chain) - 1
            features_to_add.append(new_feature)

    # Closed rings without start/end nodes
    for segment in unique_segments:
        if segment in visited_segments:
            continue
        start_node, next_node = segment
        chain = traverse_chain(start_node, next_node)
        for a, b in zip(chain[:-1], chain[1:]):
            visited_segments.add(tuple(sorted([a, b])))

        new_feature = QgsFeature(result_layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
        new_feature["src_count"] = len(chain) - 1
        features_to_add.append(new_feature)

    result_provider.addFeatures(features_to_add)
    return result_layer


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
    polygones_merge = None  # Initialize to avoid UnboundLocalError

    shp_area2(grouped_bdgs)
    for feature in grouped_bdgs.getFeatures():

        fid = feature.id()


        shapeareagroup = feature['Area']
        if shapeareagroup is None or shapeareagroup == 0:
            Logger.log(f"Feature {fid}: Area is None or 0, skipping", level="WARNING")
            continue
        single_feature = QgsFeature(feature)

        # Neues temporäres Layer erstellen
        temporary_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", f"temp_feature_{fid}", "memory")
        provider = temporary_layer.dataProvider()

        # Füge das Feature zum temporären Layer hinzu
        provider.addFeatures([single_feature])

        # Geometrie reparieren, um ungültige Geometrien abzufangen
        temporary_layer = processing.run("native:fixgeometries", {
            'INPUT': temporary_layer,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        #outline_points_list = []
        outline_points = processing.run(
            "native:extractvertices",
            {
                'INPUT': temporary_layer,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
        )['OUTPUT']

        outline_points = delete_first_point(outline_points)

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

        road_network_sel = _build_minimized_lines_from_selection(road_network_sel, crs)

        hu_ortho = create_shortest_lines_to_roads(outline_points, road_network_sel)

        hu_ortho_filter = filter_ortho_lines(hu_ortho)

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
