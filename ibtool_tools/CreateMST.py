#from PyQt5.QtGui.QRawFont import weight
from PyQt5.QtGui import QRawFont
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsLineString,
    QgsProject,
    QgsDistanceArea,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    edit
)
from qgis.PyQt.QtCore import QVariant
import scipy.spatial.distance as spd
import networkx as nx
import numpy as np
from scipy.spatial import Delaunay
import math

from ..helpers.logger import Logger
from ..helpers.system_utils import save_temp_layer_to_gpkg, msg
from ..helpers.geometry_utils import create_linestring_from_array

def calculate_mst(input_bdg, streets, SpatialReference, road_length=50):
    """
    Calculate the Minimum Spanning Tree (MST) from building points, considering streets as constraints.
    Edges crossing roads longer than the threshold are excluded.

    :param input_bdg: Path to the buildings shapefile.
    :param streets: Path to the streets shapefile.
    :param part_name: Name for intermediate and output layers.
    :param road_length: Threshold for excluding edges crossing roads (default is 50 meters).
    :return: Path to the resulting MST shapefile.
    """

    def unique(items):
        """Returns a list of unique elements."""
        return list(set(tuple(item) for item in items))

    def create_layer_from_edges(edges, crs):
        """Create a line layer from edge data."""
        layer = QgsVectorLayer("LineString?crs={}".format(crs.toWkt()), "MST_Lines", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("weight", QVariant.Double)
        ])
        layer.updateFields()

        features = []
        for edge in edges:
            [x1, y1], [x2, y2], weight = edge
            geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
            feature = QgsFeature()
            feature.setGeometry(geom)
            feature.setAttributes([weight])
            features.append(feature)

        provider.addFeatures(features)
        return layer

    def join_array_to_polygons(
            input_bdg,
            daten_array: list,
            feldname: str = "node",
            toleranz: float = 0.0001
    ):
        """
        Lädt einen Polygonlayer und verknüpft über Zentroiden-Koordinaten Werte aus einem Array.

        :param input_bdg: Gebäudepolygone
        :param daten_array: Liste im Format [[x, y, zahl1, zahl2], ...]
        :param feldname: Name des Feldes
        :param toleranz: Toleranz beim Koordinatenvergleich der Zentroiden
        """
        # Layer laden
        layer = input_bdg


        # Attribute hinzufügen, falls nicht vorhanden
        feldnamen = [f.name() for f in layer.fields()]
        with edit(layer):
            if feldname not in feldnamen:
                layer.dataProvider().addAttributes([QgsField(feldname, QVariant.String)])

        # Feature aktualisieren
        with edit(layer):
            for feature in layer.getFeatures():
                centroid = feature.geometry().centroid().asPoint()
                for x, y, node in daten_array:
                    if abs(centroid.x() - x) < toleranz and abs(centroid.y() - y) < toleranz:
                        feature[feldname] = node
                        layer.updateFeature(feature)
                        break  # passenden Eintrag gefunden → nächstes Feature

    def polygon_stuetzpunkte_dict(input_bdg, feldname):
        """
        Erstellt ein Dictionary mit den Werten von feldname1 als Schlüssel
        und den Polygon-Stützpunkten als Werteliste.

        :param input_bdg: Ein QgsVectorLayer mit Polygon-Geometrie
        :param feldname: Name des Felds, das als Dictionary-Schlüssel verwendet wird
        :return: Dictionary {wert: [(x1, y1), (x2, y2), ...]}
        """
        result_dict = {}

        for feature in input_bdg.getFeatures():
            key = feature[feldname]
            geometry = feature.geometry()

            # Nur mit Polygonen arbeiten
            if geometry.isMultipart():
                polygons = geometry.asMultiPolygon()
            else:
                polygons = [geometry.asPolygon()]

            # Alle Ringe in allen Polygonteilen extrahieren (äußere + evtl. innere Ringe)
            stützpunkte = []
            for polygon_part in polygons:
                for ring in polygon_part:
                    for pt in ring:
                        stützpunkte.append((pt.x(), pt.y()))

            result_dict[key] = stützpunkte

        return result_dict



    crs = SpatialReference

    # Extract building points
    building_points = []
    for feature in input_bdg.getFeatures():
        geom = feature.geometry()
        if geom.isMultipart():
            polygons = geom.asMultiPolygon()
            for polygon in polygons:
                centroid = QgsGeometry.fromPolygonXY(polygon).centroid().asPoint()
                building_points.append([centroid.x(), centroid.y()])
        else:
            centroid = geom.centroid().asPoint()
            building_points.append([centroid.x(), centroid.y()])

    points_array = np.array(building_points)
    #[[441517.87835061 5842552.27960158][441522.42535928 5842556.40760104][441538.48145923 5842529.0131073]]
    tri = Delaunay(points_array)
    msg("delaunay")

    # Create graph from Delaunay edges
    graph = nx.Graph()
    edges = []
    for simplex in tri.simplices:
        #[[252 292 291][1992 1827 1989][1621 218 233]]
        for i in range(3):
            p1 = simplex[i]
            p2 = simplex[(i + 1) % 3]
            point1 = points_array[p1]
            point2 = points_array[p2]
            dist = np.linalg.norm(point1 - point2)
            graph.add_edge(p1, p2, weight=dist)
            edges.append([[point1[0], point1[1]], [point2[0], point2[1]], dist])

    DelaunayList = []
    list_of_points = []
    ListOfPointsAndNodes = []


    nr_of_points = len(points_array)

    for x in range(0, nr_of_points):
        o = [0, 0]
        list_of_points.append(o)

    # Transfer of the edges of the Delaunay triangulation into a list

    for x in range(len(tri.simplices)):  # tri.simplices contain three nodes each
        list_of_points[tri.simplices[x, 0]] = points_array[tri.simplices[x, 0]].tolist()  # coordinates (xy) of the first node
        list_of_points[tri.simplices[x, 1]] = points_array[tri.simplices[x, 1]].tolist()
        list_of_points[tri.simplices[x, 2]] = points_array[tri.simplices[x, 2]].tolist()

        x0, y0 = points_array[tri.simplices[x, 0]]
        x1, y1 = points_array[tri.simplices[x, 1]]
        x2, y2 = points_array[tri.simplices[x, 2]]

        if int(tri.simplices[x, 0]) < int(tri.simplices[x, 1]):  # arrange the node pairs
            e1 = [tri.simplices[x, 0], tri.simplices[x, 1]]
            DelaunayList.append([str(e1), x0, y0, x1, y1])

        else:
            e1 = [tri.simplices[x, 1], tri.simplices[x, 0]]
            DelaunayList.append([str(e1), x1, y1, x0, y0])

        if int(tri.simplices[x, 0]) < int(tri.simplices[x, 2]):
            e2 = [tri.simplices[x, 0], tri.simplices[x, 2]]
            DelaunayList.append([str(e2), x0, y0, x2, y2])
        else:
            e2 = [tri.simplices[x, 2], tri.simplices[x, 0]]
            DelaunayList.append([str(e2), x2, y2, x0, y0])

        if int(tri.simplices[x, 1]) < int(tri.simplices[x, 2]):
            e3 = [tri.simplices[x, 1], tri.simplices[x, 2]]
            DelaunayList.append([str(e3), x1, y1, x2, y2])
        else:
            e3 = [tri.simplices[x, 2], tri.simplices[x, 1]]
            DelaunayList.append([str(e3), x2, y2, x1, y1])

        ListOfPointsAndNodes.append([x0, y0, int(tri.simplices[x, 0])])
        ListOfPointsAndNodes.append([x1, y1, int(tri.simplices[x, 1])])
        ListOfPointsAndNodes.append([x2, y2, int(tri.simplices[x, 2])])


    a = unique(ListOfPointsAndNodes)
    ListOpPointsAndNodes = a

    a = unique(DelaunayList)
    DelaunayList = a

    #nodes werden in der Attributabelle der Gebäude als extra spalte eingetragen

    join_array_to_polygons(input_bdg, ListOpPointsAndNodes)
    save_temp_layer_to_gpkg(input_bdg, "input_bdg_42")

    DictListOfNodes = polygon_stuetzpunkte_dict(input_bdg, "node")

    # Initialisiere Graph
    G = nx.Graph()

    # Durchlaufe alle Einträge
    for entry in DelaunayList:
        edge_str = entry[0]
        #node1_str, node2_str = edge_str.split()
        #node1, node2 = int(node1_str), int(node2_str)

        #edge_str = str(z[4])
        string2 = edge_str.replace("[", "")
        string3 = string2.replace("]", "")
        string = string3.replace(" ", "")
        node1, node2 = string.split(",", 1)


        XA = DictListOfNodes[node1]
        XB = DictListOfNodes[node2]

        # Distanzmatrix berechnen
        distances = spd.cdist(XA, XB, metric='euclidean')
        min_dist = distances.min()
        weight = max(min_dist, 1)  # Falls kleiner als 1, setze auf 1

        # Kante hinzufügen
        G.add_edge(node1, node2, weight=weight)

    mst = nx.minimum_spanning_edges(G, data=True)  # a generator of MST edges
    edgelist = list(mst)  # make a list of the edges
    ArrayOfLines = []
    for x in range(len(edgelist)):
        p1, p2, w = edgelist[x]
        weight = w['weight']
        x1, y1 = list_of_points[int(p1)]
        x2, y2 = list_of_points[int(p2)]
        ArrayOfLines.append([[x1, y1], [x2, y2], weight])
    mst_polyline = create_linestring_from_array(ArrayOfLines, crs,  "mst_poly")
    save_temp_layer_to_gpkg(mst_polyline, "mst_polyline")


    # Filter edges that cross streets longer than road_length
    filtered_edges = []
    distance_area = QgsDistanceArea()
    for edge in edges:
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(*edge[0]), QgsPointXY(*edge[1])])
        intersects_long_road = False
        for road_feature in streets.getFeatures():
            road_geom = road_feature.geometry()
            if distance_area.measureLength(road_geom) > road_length and geom.crosses(road_geom):
                intersects_long_road = True
                break
        if not intersects_long_road:
            filtered_edges.append(edge) # [[441478.54240229557, 5841087.986828695], [441404.05341359985, 5841021.432969372], 99.89006771312381]

    filtered_edges_layer = create_layer_from_edges(filtered_edges, crs)
    save_temp_layer_to_gpkg(filtered_edges_layer, "MST2_42")

    # Generate Minimum Spanning Tree
    mst_edges = nx.minimum_spanning_edges(graph, data=True)
    mst_edge_list = []
    for u, v, data in mst_edges:
        point1 = points_array[u]
        point2 = points_array[v]
        mst_edge_list.append([[point1[0], point1[1]], [point2[0], point2[1]], data['weight']])

    # Create output layer
    mst_layer = create_layer_from_edges(mst_edge_list, crs)


    return mst_layer

# Example usage:
# result_path = calculate_mst("path/to/buildings.shp", "path/to/streets.shp", "output", road_length=50)
# print(f"MST shapefile saved at: {result_path}")
