
from operator import itemgetter
import numpy as np
import math

from PyQt5.QtCore import QVariant
from qgis import processing
from qgis.core import (
    QgsGeometry, 
    QgsPoint, 
    QgsFeature, 
    QgsVectorLayer,
    QgsField,
    QgsProcessing,
    QgsWkbTypes,
    QgsPointXY
)

from ..helpers.system_utils import get_feature_count
from ..helpers.logger import Logger
from ..helpers.geometry_utils import add_area_field_and_calculate, shp_area, create_empty_layer


def calc_bounding_rect(hu_polyline: list[tuple[float, float]] | object, hu_layer: object, type: str, crs: object) -> \
tuple[object, float | None]:
    """
    Calculate the bounding rectangle for a given polyline or layer.

    This function determines a bounding rectangle based on the provided inputs. The
    primary focus is to calculate the rectangle's main orientation by analyzing
    line directions and aggregating line segments. Once the orientation is calculated,
    the function computes the bounding rectangle that encompasses the polyline or
    layer geometry.

    :param hu_polyline: The input polyline data, which could either be a list of
        coordinates or a more structured layer object.
    :param hu_layer: The data structure containing feature information of the layer.
        This parameter is assessed when type is set to "shape".
    :param type: A string indicating the type of input provided:
        - "shape": The input is interpreted as a structured spatial layer.
        - "list": The input is interpreted as a list of coordinate and segment-related
          data.
    :param crs: The coordinate reference system in which the bounding rectangle
        should be calculated, ensuring spatial consistency.
    :return: The calculated bounding rectangle in the form of its corner points and
        orientation.
    :rtype: list[tuple[float, float]] or dict
    """

    LengthList = []
    AngleList = []
    PointList = []

    def main_angle(list, maxdiff):
        """
        Calculate the main angle from a list of angle-length pairs.

        This function groups angle-length pairs based on a maximum difference threshold
        (maxdiff) between angles. The group with the largest cumulative length is then
        analyzed, and the angle corresponding to the longest subsequence within that
        group is returned as the main angle.

        :param list: A list of tuples, where each tuple contains an angle (float) and
            its corresponding length (float).
        :param maxdiff: The maximum difference allowed between angles for grouping
            them together.
        :type list: list[tuple[float, float]]
        :type maxdiff: float
        :return: The angle (float) representing the main angle calculated based on the
            given criteria.
        :rtype: float
        """
        sorted_angles = sorted(list, key=itemgetter(0))
        groups = [[sorted_angles[0]]]
        for x in sorted_angles[1:]:
            if abs(x[0] - groups[-1][-1][0]) < maxdiff:
                groups[-1].append(x)
            else:
                groups.append([x])
        sumlist = []
        for e in groups:
            s = 0
            for j in e:
                s = s + j[1]
            sumlist.append(s)

        max_sum_group = groups[np.argmax(sumlist)]
        s = 0
        g1 = max_sum_group[0][0]
        lengthsum = []
        for e in max_sum_group:
            if g1 == e[0]:
                s = s + e[1]
            else:
                lengthsum.append(s)
                s = e[1]
            g1 = e[0]
        if len(lengthsum) == 0:
            lengthsum.append(s)
        MainAng = max_sum_group[np.argmax(lengthsum)][0]

        return MainAng


    def near_point(x0, y0, x1, y1, x2, y2):
        """
        Computes the perpendicular distance of a point from a line segment
        and calculates the nearest point on the segment to the given point.
        The function uses vector mathematics to derive the results.

        :param x0: x-coordinate of the first point of the line segment
        :param y0: y-coordinate of the first point of the line segment
        :param x1: x-coordinate of the second point of the line segment
        :param y1: y-coordinate of the second point of the line segment
        :param x2: x-coordinate of the point whose distance and nearest
            projection on the line segment are to be determined
        :param y2: y-coordinate of the point whose distance and nearest
            projection on the line segment are to be determined
        :return: A tuple where:
            - The first element is the perpendicular distance of the given
              point to the line segment
            - The second and third elements are the x- and y-coordinates of
              the nearest point on the line segment
        """

        p0 = np.array([x0, y0])
        p1 = np.array([x1, y1])
        p2 = np.array([x2, y2])

        d = np.abs(np.cross(p1 - p0, p0 - p2) / np.linalg.norm(p1 - p0))

        dx = x1 - x0
        dy = y1 - y0
        m = np.sqrt(dx * dx + dy * dy)
        dx /= m
        dy /= m

        l = (dx * (x2 - x0)) + (dy * (y2 - y0))
        x = (dx * l) + x0
        y = (dy * l) + y0

        return d, x, y

    def vector_angle(xy11, xy12, xy21, xy22):
        """
        Calculates the angle between two vectors formed by the given points.

        The function determines the central point from the input points to correctly
        define the vectors. It computes the angle between these vectors using the
        dot product and converts the angle from radians to degrees. Additionally, it
        adjusts the angle direction based on specific positional conditions.

        :param xy11: Tuple representing the first point (x, y) of the first vector.
        :param xy12: Tuple representing the second point (x, y) of the first vector.
        :param xy21: Tuple representing the first point (x, y) of the second vector.
        :param xy22: Tuple representing the second point (x, y) of the second vector.
        :return: The angle in degrees between the two vectors in the defined direction.
        :rtype: float
        """
        # Sort the points by central point
        List = xy11, xy12, xy21, xy22

        if List.count(List[0]) == 2:  # xy11 is central point
            if xy21 != xy11:
                xy21b = xy21
                xy21 = xy22
                xy22 = xy21b

        else:  # xy12 is central point
            xy11b = xy11
            xy11 = xy12
            xy12 = xy11b
            if xy21 != xy11:
                xy21b = xy21
                xy21 = xy22
                xy22 = xy21b

        # Conversion of point pairs into position vectors
        x1, y1 = xy12[0] - xy11[0], xy12[1] - xy11[1]
        x2, y2 = xy22[0] - xy21[0], xy22[1] - xy21[1]

        Vector1 = np.array([x1, y1])
        Vector2 = np.array([x2, y2])
        dot = np.dot(Vector1, Vector2)
        x_modulus = np.sqrt((Vector1 * Vector1).sum())
        y_modulus = np.sqrt((Vector2 * Vector2).sum())
        cos_angle = dot / x_modulus / y_modulus
        angle = np.arccos(cos_angle)  # angle in rad
        Ang = angle * 360 / 2 / np.pi  # angle in degrees

        if xy11[1] == xy22[1]:  # Direction is calculated
            if Vector1[1] <= 0:
                Ang = 180 - Ang

        return Ang



    if type == "shape":
        for feat in hu_polyline.getFeatures():
            X11 = feat.geometry().vertexAt(0).x()
            Y11 = feat.geometry().vertexAt(0).y()
            X12 = feat.geometry().vertexAt(1).x()
            Y12 = feat.geometry().vertexAt(1).y()
            LENGHTH = feat.geometry().length()
            Angle = vector_angle((X11, Y11), (X12, Y12), (X11, Y11), (X11 + 100, Y11))
            LengthList.append(LENGHTH)
            AngleList.append(Angle)
            PointList.append([X11, Y11])

    if type == "list":
        for row in hu_polyline:
            X11, Y11, X12, Y12, LENGHTH = row
            Angle = vector_angle((X11, Y11), (X12, Y12), (X11, Y11), (X11 + 100, Y11))
            LengthList.append(LENGHTH)
            AngleList.append(round(Angle, 1))
            PointList.append([X11, Y11])



    j = 0
    list = []
    for i in AngleList:
        list.append([i, LengthList[j]])
        j += 1


    if len(PointList) > 4:
        MainAngle = main_angle(list, 10)

        X, Ymin = min(PointList, key=lambda t: t[1])
        Xmax, Y = max(PointList, key=lambda t: t[0])
        Xmin, Y = min(PointList, key=lambda t: t[0])

        Py1 = Ymin

        if MainAngle > 90:
            Px1 = Xmax + 10000
        else:
            Px1 = Xmin - 10000

        Px2 = Px1 + 10000 * math.cos(math.radians(MainAngle))
        Py2 = Py1 + 10000 * math.sin(math.radians(MainAngle))

        NearList = []
        for p in PointList:
            d, x, y = near_point(Px1, Py1, Px2, Py2, p[0], p[1])
            NearList.append([d, p[0], p[1], x, y])

        A_NEAR_DIST, A_FROM_X, A_FROM_Y, A_NEAR_X, A_NEAR_Y = min(NearList, key=itemgetter(0))
        B_NEAR_DIST, B_FROM_X, B_FROM_Y, B_NEAR_X, B_NEAR_Y = max(NearList, key=itemgetter(0))
        C_NEAR_DIST, C_FROM_X, C_FROM_Y, C_NEAR_X, C_NEAR_Y = min(NearList, key=itemgetter(4))
        D_NEAR_DIST, D_FROM_X, D_FROM_Y, D_NEAR_X, D_NEAR_Y = max(NearList, key=itemgetter(4))

        C2_x = C_NEAR_X + ((C_FROM_X - C_NEAR_X) * B_NEAR_DIST / C_NEAR_DIST)
        C2_y = C_NEAR_Y + ((C_FROM_Y - C_NEAR_Y) * B_NEAR_DIST / C_NEAR_DIST)
        D2_x = D_NEAR_X + ((D_FROM_X - D_NEAR_X) * B_NEAR_DIST / D_NEAR_DIST)
        D2_y = D_NEAR_Y + ((D_FROM_Y - D_NEAR_Y) * B_NEAR_DIST / D_NEAR_DIST)
        D1_x = D_NEAR_X + ((D_FROM_X - D_NEAR_X) * A_NEAR_DIST / D_NEAR_DIST)
        D1_y = D_NEAR_Y + ((D_FROM_Y - D_NEAR_Y) * A_NEAR_DIST / D_NEAR_DIST)
        C1_x = C_NEAR_X + ((C_FROM_X - C_NEAR_X) * A_NEAR_DIST / C_NEAR_DIST)
        C1_y = C_NEAR_Y + ((C_FROM_Y - C_NEAR_Y) * A_NEAR_DIST / C_NEAR_DIST)

        ArrayOfLines = [[[C1_x, C1_y], [C2_x, C2_y]], [[C2_x, C2_y], [D2_x, D2_y]],
                        [[D2_x, D2_y], [D1_x, D1_y, ]], [[D1_x, D1_y], [C1_x, C1_y]]]

        PolyArea = math.sqrt(abs(C1_x - C2_x) ** 2 + abs(C1_y - C2_y) ** 2) * math.sqrt(
            abs(D2_x - C2_x) ** 2 + abs(D2_y - C2_y) ** 2)

        # Create a polygon from ArrayOfLines
        HUDirRect_geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(point[0], point[1]) for point in ArrayOfLines[0]] +
             [QgsPointXY(point[0], point[1]) for point in ArrayOfLines[1]] +
             [QgsPointXY(point[0], point[1]) for point in ArrayOfLines[2]] +
             [QgsPointXY(point[0], point[1]) for point in ArrayOfLines[3]]]
        )

        # Create a memory layer for the polygon
        HUDirRect = QgsVectorLayer(f'Polygon?crs={crs.authid()}', "HUDirRect", "memory")
        provider = HUDirRect.dataProvider()

        # Add fields to the layer
        provider.addAttributes([QgsField("id", QVariant.Int)])
        HUDirRect.updateFields()

        # Add the polygon geometry to the layer
        feature = QgsFeature()
        feature.setGeometry(HUDirRect_geom)
        feature.setAttributes([1])  # Example attribute
        provider.addFeature(feature)

        HUDirRect.commitChanges()
        

        if PolyArea == 0:
            Logger.log(" FID {} or FID {} in MST_Clustering causes division by zero", level="CRITICAL")
            PolyArea = 1000000000000
        return HUDirRect, PolyArea

    else:
        Logger.log("CalcBoundingRect - No output generated", level="WARNING")

        return hu_layer, None


def mst_clustering(hu_layer, mst_layer, crs, overlap_ratio=18, ):
    """
    Performs clustering using a Minimum Spanning Tree (MST) approach combined with spatial analysis to group
    geospatial entities based on their overlapping areas and bounding rectangle ratio.

    This function processes two input geospatial layers, `hu_layer` and `mst_layer`, combining their spatial
    properties and attributes with additional calculations to identify clusters. The clustering process
    relies on calculating areas, centroid points, edges, and joining the attributes of polygons and the MST.

    The resulting clustered groups are determined based on a defined overlap ratio threshold, representing the
    percentage of area occupied in a bounding rectangle by the entities in a cluster.

    :param hu_layer: The main layer representing spatial features for the clustering process.
        It could include polygons with attributes such as area and function.
    :param mst_layer: A layer representing the Minimum Spanning Tree for the spatial features in the `hu_layer`.
        It primarily contains edges or connections between entities for clustering.
    :param crs: A coordinate reference system object used for all geospatial calculations and layer manipulations.
    :param overlap_ratio: A numeric value (default is 18) representing the minimum bounding rectangle
        overlap ratio percentage that entities in a cluster must meet to be considered valid.
    :return: None
    """

    mst_layer = processing.run("native:extractbylocation",
                   {'INPUT': mst_layer,
                    'PREDICATE': [0],
                    'INTERSECT': hu_layer,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']
    add_area_field_and_calculate(hu_layer)

    edges = []  # Liste für Kanteninformationen

    for feature in hu_layer.getFeatures():
        geom = feature.geometry()

        # Sicherstellen, dass Geometrie gültig ist und ein Polygon darstellt
        if geom.isGeosValid() and geom.type() == QgsWkbTypes.PolygonGeometry:
            if geom.isMultipart():
                polygons = geom.asMultiPolygon()
            else:
                polygons = [geom.asPolygon()]

            for polygon in polygons:
                for ring in polygon:
                    # Debug: Anzahl der Punkte im Ring überprüfen
                    if not ring:
                        Logger.log(f"Feature ID {feature.id()} has an empty ring", level="WARNING")
                        continue  # Überspringe leere Ringe

                    for i in range(len(ring) - 1):
                        try:
                            # Punkte initialisieren
                            start_point = QgsPointXY(ring[i])  # Startpunkt
                            end_point = QgsPointXY(ring[i + 1])  # Endpunkt

                            # Länge der Kante berechnen
                            edge_length = QgsPoint(start_point).distance(QgsPoint(end_point))

                            # Kanteninformationen hinzufügen (Feature-ID, Startpunkt, Endpunkt, Kantenlänge)
                            edges.append([
                                feature.id(),  # ID des ursprünglichen Gebäudepolygons
                                start_point.x(),
                                start_point.y(),
                                end_point.x(),
                                end_point.y(),
                                edge_length
                            ])
                        except Exception as e:
                            Logger.log(f"Error processing edge for feature ID {feature.id()}: {str(e)}", level="WARNING")
                            continue
        else:
            # Geometrien, die keiner Polygongeometrie entsprechen, überspringen
            Logger.log(f"Invalid or unsupported geometry type for feature ID {feature.id()}", level="WARNING")

    HULineListSort = sorted(edges, key=itemgetter(0))
    HULineArray = []
    sublist = []
    j = HULineListSort[0][0]
    for i in HULineListSort:
        FID_ORIG, x1, y1, x2, x2, L = i
        if FID_ORIG == j:
            sublist.append(i[1:])
        else:
            HULineArray.append([j, sublist])
            sublist = []
            sublist.append(i[1:])
        j = FID_ORIG
    HULineArray.append([j, sublist])
    dict_HU = dict(list(HULineArray))

    hu_layer = shp_area(hu_layer, "Area")

    hu_layer.dataProvider().addAttributes([QgsField("fid_hu_orig", QVariant.Int)])
    hu_layer.updateFields()

    hu_layer = processing.run("native:fieldcalculator",
                   {'INPUT': hu_layer,
                    'FIELD_NAME': 'fid_hu_orig',
                    'FIELD_TYPE': 0,
                    'FIELD_LENGTH': 0,
                    'FIELD_PRECISION': 0,
                    'FORMULA': '@id',
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']

    mst_layer.dataProvider().addAttributes([QgsField("fid_mst_orig", QVariant.Int)])
    mst_layer.updateFields()

    mst_layer = processing.run("native:fieldcalculator",
                              {'INPUT': mst_layer,
                               'FIELD_NAME': 'fid_mst_orig',
                               'FIELD_TYPE': 0,
                               'FIELD_LENGTH': 0,
                               'FIELD_PRECISION': 0,
                               'FORMULA': '@id',
                               'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                               })['OUTPUT']

    hu_points = processing.run("native:centroids",
                               {'INPUT': hu_layer,
                                'ALL_PARTS': False,
                                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                })['OUTPUT']

    #save_temp_layer_to_gpkg(hu_points, "hu_points_43")


    mst_layer_hu_join = processing.run("native:joinattributesbylocation",
                   {'INPUT': mst_layer,
                    'PREDICATE': [0],
                    'JOIN': hu_points,
                    'JOIN_FIELDS': ['fid_hu_orig', 'fktkurz', 'fkt', 'Area'],
                    'METHOD': 0,
                    'DISCARD_NONMATCHING': False,
                    'PREFIX': '',
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']

    MST_List = []
    empty_polygon_layer = create_empty_layer("Polygon", crs.authid())
    merge_layer_2 = create_empty_layer("Polygon", crs.authid())
    
    mst_layer_hu_join_features = mst_layer_hu_join.getFeatures()
    for feature in mst_layer_hu_join_features:
        TARGET_FID = feature["fid_mst_orig"] # id des MST-Features
        ORIG_FID = feature["fid_hu_orig"] # eigentlich "fid"
        MST_DIFF = feature["weight"]
        Area = feature["Area"]
        MST_List.append([TARGET_FID, ORIG_FID, MST_DIFF, Area])  # ORIG_FID-1 because of file typ change

    ORIG_FID2 = 0
    Area2 = 0
    MST_Pair_List = []
    dict_FID_Area = {}
    j = "x"

    ListOutsorted = []
    # sorted from shortest MST_DIFF to longest

    MST_List_Sort = sorted(MST_List, key=itemgetter(0))

    for i in MST_List_Sort:
        TARGET_FID, ORIG_FID1, MST_DIFF, Area1 = i
        if TARGET_FID == j:
            MST_Pair_List.append([MST_DIFF, Area1, Area2, ORIG_FID1, ORIG_FID2])
        j = TARGET_FID
        dict_FID_Area[ORIG_FID1] = Area1
        ORIG_FID2 = ORIG_FID1
        Area2 = Area1

    # MST_Pair_List = MST_Pair_List[:]
    dict_member_groub = {}
    dict_group_all_members = {}

    MST_Pair_List_Sort = sorted(MST_Pair_List, key=itemgetter(0))

    group_number = 0
    for element in MST_Pair_List_Sort:
        MST_DIFF, Area1, Area2, ORIG_FID1, ORIG_FID2 = element
        groupestatus = False
        # if there is only one ORIG_FID continue with next element
        if ORIG_FID1 in dict_HU and ORIG_FID2 in dict_HU:
            pass
        else:
            Logger.log("fid in MST_Cluster missing", level="WARNING")
            continue
        # one Bdg is already member of a group
        if ORIG_FID1 in dict_member_groub or ORIG_FID2 in dict_member_groub:
            if ORIG_FID1 in dict_member_groub:
                group_id = dict_member_groub[ORIG_FID1]
                new_FID = ORIG_FID2
            else:
                group_id = dict_member_groub[ORIG_FID2]
                new_FID = ORIG_FID1
            members_group_id = dict_group_all_members[group_id][:]
            members_group_id.extend([new_FID])
            members_group_id_coords = []

            for i in members_group_id:
                members_group_id_coords.extend(dict_HU[i])

            Rect, AreaRect = calc_bounding_rect(members_group_id_coords, empty_polygon_layer, "list", crs)
            sumarea = 0
            for i in members_group_id:
                sumarea = dict_FID_Area[i] + sumarea

            Ratio = sumarea / AreaRect * 100

            if Ratio > overlap_ratio:
                dict_group_all_members[group_id] = members_group_id
                dict_member_groub[new_FID] = group_id
                groupestatus = True

            else:
                pass
                # check if small group is possible
                ListOutsorted.append(["G", ORIG_FID1, ORIG_FID2])

        if (ORIG_FID1 in dict_member_groub or ORIG_FID2 in dict_member_groub) is not True or groupestatus is False:

            if ORIG_FID1 in dict_HU:
                Coords1 = dict_HU[ORIG_FID1][:]
            else:
                Logger.log("Error in dict_HU:{} was not found".format(ORIG_FID1), level="CRITICAL")
                continue
            if ORIG_FID2 in dict_HU:
                Coords2 = dict_HU[ORIG_FID2][:]
            else:
                Logger.log("Error in dict_HU:{} was not found".format(ORIG_FID2), level="CRITICAL")
                continue
            Coords1.extend(Coords2)

            Rect, AreaRect = calc_bounding_rect(Coords1, empty_polygon_layer, "list", crs)
            Ratio = (Area1 + Area2) / AreaRect * 100

            if Ratio > overlap_ratio:
                dict_member_groub[ORIG_FID1] = group_number
                dict_member_groub[ORIG_FID2] = group_number
                dict_group_all_members[group_number] = [ORIG_FID1, ORIG_FID2]
                group_number = group_number + 1
            else:
                ListOutsorted.append(["S", ORIG_FID1, ORIG_FID2])

    for single_group in dict_group_all_members:
        single_group_list = dict_group_all_members[single_group][:]
        members_group_id_coords = []
        for j in single_group_list:
            members_group_id_coords.extend(dict_HU[j])

        Rect, AreaRect = calc_bounding_rect(members_group_id_coords, empty_polygon_layer, "list", crs)
        #save_temp_layer_to_gpkg(Rect, "Rect_{}".format(j))

        try:
            rect_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [Rect, merge_layer_2],
                'CRS': crs,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
            merge_layer_2 = rect_merge
        except:
            if single_group_list is not None:
                Logger.log("Group could not merged: {}".format(single_group_list), level="SUCCESS")
            else:
                Logger.log("Group could not merged: None-Type", level="SUCCESS")

    return rect_merge
