from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsDistanceArea,
    edit,
    QgsProcessing,
)
from qgis.PyQt.QtCore import QVariant
import scipy.spatial.distance as spd
import networkx as nx
import numpy as np
from scipy.spatial import Delaunay
from qgis import processing
from ..helpers.system_utils import save_temp_layer_to_gpkg
from ..helpers.geometry_utils import create_linestring_layer_from_array, nodes_detect
from ..helpers.logger import Logger

def calculate_mst(input_bdg, streets_orig, SpatialReference, road_length=50):
    """
    Calculates Minimum Spanning Tree (MST) and processes spatial data for street and building layers.
    Performs operations such as Delaunay triangulation, node detection, dead-end street calculations,
    and adds fields to and manipulates geographic layers.

    :param input_bdg: QgsVectorLayer representing building polygons.
    :param streets_orig: QgsVectorLayer representing the original street layer.
    :param SpatialReference: Object specifying the spatial reference system (CRS) to use.
    :param road_length: Optional; numerical threshold to filter streets by length, default is 50.
    :return: None
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
            stuetzpunkte = []
            for polygon_part in polygons:
                for ring in polygon_part:
                    for pt in ring:
                        stuetzpunkte.append((pt.x(), pt.y()))

            result_dict[key] = stuetzpunkte

        return result_dict

    # Hilfsfunktion: Koordinaten runden und normalisieren
    def rounded_edge_key(x1, y1, x2, y2):
        p1 = (round(x1, 0), round(y1, 0))
        p2 = (round(x2, 0), round(y2, 0))
        return tuple(sorted([p1, p2]))  # Reihenfolge-unabhängig


    crs = SpatialReference

    save_temp_layer_to_gpkg(streets_orig, "streets_orig")
    streets = QgsVectorLayer("LineString?crs={}".format(streets_orig.crs().authid()), "streets", "memory")
    data_provider = streets.dataProvider()
    data_provider.addFeatures(list(streets_orig.getFeatures()))
    streets.updateExtents()

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

    edges = []
    for simplex in tri.simplices:
        #[[252 292 291][1992 1827 1989][1621 218 233]]
        for i in range(3):
            p1 = simplex[i]
            p2 = simplex[(i + 1) % 3]
            point1 = points_array[p1]
            point2 = points_array[p2]
            dist = np.linalg.norm(point1 - point2)
            edges.append([[point1[0], point1[1]], [point2[0], point2[1]], dist])

    delaunay_triangles = create_layer_from_edges(edges, crs)

    nodes_1 = nodes_detect(streets, 1)
    
    schnittpunkte = processing.run("native:lineintersections",
                   {'INPUT': streets,
                    'INTERSECT': streets,
                    'INPUT_FIELDS': [], 'INTERSECT_FIELDS': [], 'INTERSECT_FIELDS_PREFIX': '',
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    schnittpunkte_puffer = processing.run("native:buffer", {
        'INPUT': schnittpunkte,
        'DISTANCE': 5, 'SEGMENTS': 5, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2, 'DISSOLVE': False,
        'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    sel_nodes_1 = processing.run("native:selectbylocation", {
        'INPUT': nodes_1,
        'PREDICATE': [0],
        'INTERSECT': schnittpunkte_puffer,
        'METHOD': 0,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    with edit(nodes_1):
        for feature in nodes_1.getFeatures():
            if feature.id() in nodes_1.selectedFeatureIds():  # Nur ausgewählte Features löschen
                nodes_1.deleteFeature(feature.id())

    streets_dead_end = processing.run("native:extractbylocation",
                   {'INPUT': streets,
                    'PREDICATE': [0],
                    'INTERSECT': nodes_1,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']

    # Add a new field 'length' to the 'streets_dead_end' layer
    fields = streets_dead_end.fields()
    if not fields.indexFromName('length') >= 0:  # Avoid duplicate field addition
        streets_dead_end.dataProvider().addAttributes([QgsField('length', QVariant.Double)])
        streets_dead_end.updateFields()

    # Calculate and set the length for each feature in 'streets_dead_end'
    distance_area = QgsDistanceArea()
    with edit(streets_dead_end):
        for feature in streets_dead_end.getFeatures():
            geom = feature.geometry()
            length = distance_area.measureLength(geom)
            feature['length'] = length
            streets_dead_end.updateFeature(feature)

    streets_dead_end_short = processing.run("native:extractbyexpression",
                   {'INPUT': streets_dead_end,
                    'EXPRESSION': '"length" < {}'.format(str(road_length)),
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']

    sel = processing.run("native:selectbylocation",{
        'INPUT': streets,
        'PREDICATE': [3],
        'INTERSECT': streets_dead_end_short,
        'METHOD': 0,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']


    with edit(streets):
        for feature in streets.getFeatures():
            if feature.id() in streets.selectedFeatureIds():  # Nur ausgewählte Features löschen
                streets.deleteFeature(feature.id())

    sel = processing.run("native:selectbylocation", {
        'INPUT': delaunay_triangles,
        'PREDICATE': [0],
        'INTERSECT': streets,
        'METHOD': 0,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    with edit(delaunay_triangles):
        for feature in delaunay_triangles.getFeatures():
            if feature.id() in delaunay_triangles.selectedFeatureIds():  # Nur ausgewählte Features löschen
                delaunay_triangles.deleteFeature(feature.id())

    DelaunayList = []
    list_of_points = []
    ListOfPointsAndNodes = []
    #nr_of_points = len(points_array)
    nr_of_points = len(edges)

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

    # hier weitermachen: aus DelaunayList die einträge löschen, die keine entsprechung in delaunay_triangles haben

    Logger.log("DelaunayList: {}".format(len(DelaunayList)), level="DEBUG")

    # 1. Indiziere alle Linien im Layer (einmalig!)
    line_index = set()

    for feature in delaunay_triangles.getFeatures():
        geom = feature.geometry()
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            if len(line) >= 2:
                start = line[0]
                end = line[-1]
                key = rounded_edge_key(start.x(), start.y(), end.x(), end.y())
                line_index.add(key)

    # 2. Filter die DelaunayList anhand der indizierten Linien
    filtered_edges = []

    for entry in DelaunayList:
        _, x1, y1, x2, y2 = entry
        key = rounded_edge_key(x1, y1, x2, y2)
        if key in line_index:
            filtered_edges.append(entry)

    Logger.log("filtered_edges: {}".format(len(filtered_edges)), level="DEBUG")

    join_array_to_polygons(input_bdg, ListOfPointsAndNodes)
    DictListOfNodes = polygon_stuetzpunkte_dict(input_bdg, "node")

    # Initialisiere Graph
    G = nx.Graph()

    # Durchlaufe alle Einträge
    for entry in filtered_edges:
        edge_str = entry[0]
        string2 = edge_str.replace("[", "")
        string3 = string2.replace("]", "")
        string = string3.replace(" ", "")
        node1, node2 = string.split(",", 1)

        XA = DictListOfNodes[node1]
        XB = DictListOfNodes[node2]

        # Distanzmatrix berechnen
        distances = spd.cdist(XA, XB, metric='euclidean')
        weight = distances.min()

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
    mst_polyline = create_linestring_layer_from_array(ArrayOfLines, crs,  "mst_poly")


    return mst_polyline
