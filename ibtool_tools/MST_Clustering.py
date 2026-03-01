
from operator import itemgetter
import math

import numpy as np

from PyQt5.QtCore import QMetaType
from qgis import processing
from qgis.core import (
    QgsGeometry,
    QgsPoint,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsProcessing,
    QgsWkbTypes,
    QgsPointXY,
    QgsCoordinateReferenceSystem
)

from ..helpers.logger import Logger
from ..helpers.geometry_utils import shp_area, create_empty_layer
from ..helpers.debug_utils import save_debug_layer

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "03_MST_Clustering"

# Maximum angle difference (degrees) for two angles to be grouped into the same cluster.
_MAIN_ANGLE_MAX_DIFF = 10

# Extension length (map units) for constructing the oriented reference axis in bounding rect calc.
_BOUNDING_RECT_EXTENSION = 10_000

# Length of the horizontal reference vector used when measuring line orientation angles.
_REFERENCE_VECTOR_LENGTH = 100


def _main_angle(angle_length_pairs: list[tuple[float, float]], max_diff: float) -> float:
    """Determine the dominant angle from a list of angle-length pairs.

    Groups angle-length pairs by proximity (within ``max_diff`` degrees), identifies
    the group with the greatest total length, then returns the angle of the longest
    contiguous run of identical angles within that group.

    Args:
        angle_length_pairs: List of ``(angle_degrees, length)`` tuples.
        max_diff: Maximum angular difference (degrees) for two angles to belong to
            the same group.

    Returns:
        The dominant angle in degrees.
    """
    sorted_pairs = sorted(angle_length_pairs, key=itemgetter(0))
    groups = [[sorted_pairs[0]]]
    for pair in sorted_pairs[1:]:
        if abs(pair[0] - groups[-1][-1][0]) < max_diff:
            groups[-1].append(pair)
        else:
            groups.append([pair])

    group_sums = [sum(entry[1] for entry in group) for group in groups]
    max_group = groups[int(np.argmax(group_sums))]

    current_angle = max_group[0][0]
    current_sum = 0
    length_sums = []
    for entry in max_group:
        if current_angle == entry[0]:
            current_sum += entry[1]
        else:
            length_sums.append(current_sum)
            current_sum = entry[1]
        current_angle = entry[0]
    if not length_sums:
        length_sums.append(current_sum)

    return max_group[int(np.argmax(length_sums))][0]


def _near_point(
    x0: float, y0: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> tuple[float, float, float]:
    """Compute the perpendicular distance from a point to a line and its nearest point on the line.

    Uses vector projection to find the foot of the perpendicular from point P2=(x2, y2)
    onto the line defined by P0=(x0, y0) → P1=(x1, y1).

    Args:
        x0: X-coordinate of the first point defining the line.
        y0: Y-coordinate of the first point defining the line.
        x1: X-coordinate of the second point defining the line.
        y1: Y-coordinate of the second point defining the line.
        x2: X-coordinate of the query point.
        y2: Y-coordinate of the query point.

    Returns:
        Tuple of (perpendicular_distance, nearest_x, nearest_y).
    """
    p0 = np.array([x0, y0])
    p1 = np.array([x1, y1])
    p2 = np.array([x2, y2])

    distance = np.abs(np.cross(p1 - p0, p0 - p2) / np.linalg.norm(p1 - p0))

    dx = x1 - x0
    dy = y1 - y0
    magnitude = np.sqrt(dx * dx + dy * dy)
    dx /= magnitude
    dy /= magnitude

    projection_length = (dx * (x2 - x0)) + (dy * (y2 - y0))
    nearest_x = (dx * projection_length) + x0
    nearest_y = (dy * projection_length) + y0

    return distance, nearest_x, nearest_y


def _vector_angle(
    xy11: tuple[float, float],
    xy12: tuple[float, float],
    xy21: tuple[float, float],
    xy22: tuple[float, float],
) -> float:
    """Calculate the angle (degrees) between two vectors sharing a common vertex.

    Determines the shared central point from the four input points, constructs
    two direction vectors from that centre, and returns the angle between them.
    The sign is adjusted based on the relative orientation of the first vector.

    Args:
        xy11: First point of the first vector.
        xy12: Second point of the first vector.
        xy21: First point of the second vector.
        xy22: Second point of the second vector.

    Returns:
        Angle in degrees between the two vectors.
    """
    points = (xy11, xy12, xy21, xy22)

    # Normalise so that xy11 (== xy21) is the shared central vertex;
    # xy12 and xy22 are the respective direction endpoints.
    if points.count(points[0]) == 2:  # xy11 is the central point
        if xy21 != xy11:
            xy21, xy22 = xy22, xy21
    else:  # xy12 is the central point
        xy11, xy12 = xy12, xy11
        if xy21 != xy11:
            xy21, xy22 = xy22, xy21

    x1, y1 = xy12[0] - xy11[0], xy12[1] - xy11[1]
    x2, y2 = xy22[0] - xy21[0], xy22[1] - xy21[1]

    vector1 = np.array([x1, y1])
    vector2 = np.array([x2, y2])
    dot = np.dot(vector1, vector2)
    x_modulus = np.sqrt((vector1 * vector1).sum())
    y_modulus = np.sqrt((vector2 * vector2).sum())
    cos_angle = dot / x_modulus / y_modulus
    angle_rad = np.arccos(cos_angle)
    ang = angle_rad * 360 / 2 / np.pi  # convert radians to degrees

    if xy11[1] == xy22[1]:  # adjust direction
        if vector1[1] <= 0:
            ang = 180 - ang

    return ang


def calc_bounding_rect(
    hu_polyline: list[tuple[float, float]] | object,
    hu_layer: object,
    mode: str,
    crs: object,
) -> tuple[object, float | None]:
    """Calculate the minimum oriented bounding rectangle for a polyline or layer.

    Determines the dominant orientation of the input lines, then computes a
    tightly-fitted oriented bounding rectangle enclosing all input points.

    Args:
        hu_polyline: Input polyline data — either a list of ``(x1, y1, x2, y2, length)``
            rows (when ``mode="list"``) or a QgsVectorLayer with line features
            (when ``mode="shape"``).
        hu_layer: Fallback layer returned when fewer than 5 points are available.
        mode: Input format — ``"shape"`` for a QgsVectorLayer, ``"list"`` for a
            list of coordinate/length rows.
        crs: Coordinate reference system for the output layer.

    Returns:
        Tuple of (bounding_rect_layer, poly_area) where poly_area is the rectangle
        area in map units squared, or None if insufficient input points.
    """
    length_list = []
    angle_list = []
    point_list = []

    if mode == "shape":
        for feat in hu_polyline.getFeatures():
            x11 = feat.geometry().vertexAt(0).x()
            y11 = feat.geometry().vertexAt(0).y()
            x12 = feat.geometry().vertexAt(1).x()
            y12 = feat.geometry().vertexAt(1).y()
            length = feat.geometry().length()
            angle = _vector_angle(
                (x11, y11), (x12, y12),
                (x11, y11), (x11 + _REFERENCE_VECTOR_LENGTH, y11),
            )
            length_list.append(length)
            angle_list.append(angle)
            point_list.append([x11, y11])

    if mode == "list":
        for row in hu_polyline:
            x11, y11, x12, y12, length = row
            angle = _vector_angle(
                (x11, y11), (x12, y12),
                (x11, y11), (x11 + _REFERENCE_VECTOR_LENGTH, y11),
            )
            length_list.append(length)
            angle_list.append(round(angle, 1))
            point_list.append([x11, y11])

    angle_data = [[angle, length] for angle, length in zip(angle_list, length_list)]

    if len(point_list) > 4:
        dominant_angle = _main_angle(angle_data, _MAIN_ANGLE_MAX_DIFF)

        _, y_min = min(point_list, key=lambda t: t[1])
        x_max, _ = max(point_list, key=lambda t: t[0])
        x_min, _ = min(point_list, key=lambda t: t[0])

        p_y1 = y_min
        if dominant_angle > 90:
            p_x1 = x_max + _BOUNDING_RECT_EXTENSION
        else:
            p_x1 = x_min - _BOUNDING_RECT_EXTENSION

        p_x2 = p_x1 + _BOUNDING_RECT_EXTENSION * math.cos(math.radians(dominant_angle))
        p_y2 = p_y1 + _BOUNDING_RECT_EXTENSION * math.sin(math.radians(dominant_angle))

        near_list = []
        for p in point_list:
            d, x, y = _near_point(p_x1, p_y1, p_x2, p_y2, p[0], p[1])
            near_list.append([d, p[0], p[1], x, y])

        a_near_dist, a_from_x, a_from_y, a_near_x, a_near_y = min(near_list, key=itemgetter(0))
        b_near_dist, b_from_x, b_from_y, b_near_x, b_near_y = max(near_list, key=itemgetter(0))
        c_near_dist, c_from_x, c_from_y, c_near_x, c_near_y = min(near_list, key=itemgetter(4))
        d_near_dist, d_from_x, d_from_y, d_near_x, d_near_y = max(near_list, key=itemgetter(4))

        c2_x = c_near_x + ((c_from_x - c_near_x) * b_near_dist / c_near_dist)
        c2_y = c_near_y + ((c_from_y - c_near_y) * b_near_dist / c_near_dist)
        d2_x = d_near_x + ((d_from_x - d_near_x) * b_near_dist / d_near_dist)
        d2_y = d_near_y + ((d_from_y - d_near_y) * b_near_dist / d_near_dist)
        d1_x = d_near_x + ((d_from_x - d_near_x) * a_near_dist / d_near_dist)
        d1_y = d_near_y + ((d_from_y - d_near_y) * a_near_dist / d_near_dist)
        c1_x = c_near_x + ((c_from_x - c_near_x) * a_near_dist / c_near_dist)
        c1_y = c_near_y + ((c_from_y - c_near_y) * a_near_dist / c_near_dist)

        array_of_lines = [
            [[c1_x, c1_y], [c2_x, c2_y]],
            [[c2_x, c2_y], [d2_x, d2_y]],
            [[d2_x, d2_y], [d1_x, d1_y]],
            [[d1_x, d1_y], [c1_x, c1_y]],
        ]

        poly_area = (
            math.sqrt(abs(c1_x - c2_x) ** 2 + abs(c1_y - c2_y) ** 2)
            * math.sqrt(abs(d2_x - c2_x) ** 2 + abs(d2_y - c2_y) ** 2)
        )

        # Create a polygon from array_of_lines
        hu_dir_rect_geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(point[0], point[1]) for point in array_of_lines[0]] +
             [QgsPointXY(point[0], point[1]) for point in array_of_lines[1]] +
             [QgsPointXY(point[0], point[1]) for point in array_of_lines[2]] +
             [QgsPointXY(point[0], point[1]) for point in array_of_lines[3]]]
        )

        # Create a memory layer for the polygon
        hu_dir_rect = QgsVectorLayer(f'Polygon?crs={crs.authid()}', "HUDirRect", "memory")
        provider = hu_dir_rect.dataProvider()

        provider.addAttributes([QgsField("id", QMetaType.Int)])
        hu_dir_rect.updateFields()

        feature = QgsFeature()
        feature.setGeometry(hu_dir_rect_geom)
        feature.setAttributes([1])
        provider.addFeature(feature)
        hu_dir_rect.commitChanges()

        if poly_area == 0:
            Logger.log(
                "PolyArea is zero in MST_Clustering calc_bounding_rect - causes division by zero",
                level="CRITICAL",
            )
            poly_area = 1_000_000_000_000
        return hu_dir_rect, poly_area

    else:
        Logger.log("CalcBoundingRect - No output generated", level="WARNING")
        return hu_layer, None


def mst_clustering(
    hu_layer: QgsVectorLayer,
    mst_layer: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    overlap_ratio: float = 18,
    debug_mode: bool = False,
    workspace_path: str = None,
) -> QgsVectorLayer:
    """Cluster building footprints using a Minimum Spanning Tree (MST) and bounding-rectangle overlap.

    Iterates over MST edges sorted by weight and merges pairs of building polygons
    into clusters when the ratio of their combined area to the oriented bounding
    rectangle exceeds ``overlap_ratio`` percent.

    Args:
        hu_layer: Building footprint polygon layer.
        mst_layer: MST edge layer connecting building centroids.
        crs: Coordinate reference system for all spatial operations.
        overlap_ratio: Minimum area/bounding-rect ratio (percent) required for two
            features to be merged into a cluster. Default is 18.
        debug_mode: If True, saves intermediate layers as GeoPackages for
            visual step-by-step inspection. Defaults to False.
        workspace_path: Base workspace path for debug output. Required when
            ``debug_mode`` is True.

    Returns:
        A QgsVectorLayer of oriented bounding rectangles, one per identified cluster.
    """
    # Extract MST features that intersect hu features
    mst_layer = processing.run("native:extractbylocation",
                   {'INPUT': mst_layer,
                    'PREDICATE': [0],
                    'INTERSECT': hu_layer,
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']
    if debug_mode and workspace_path:
        save_debug_layer(mst_layer, _DEBUG_TOOL_NAME, "after_mst_location_filter", workspace_path)

    # Add area field and calculate area
    hu_layer = shp_area(hu_layer)

    edges = []  # list of edge information

    # Collect all polygon edge coordinates for each building feature
    for feature in hu_layer.getFeatures():
        geom = feature.geometry()

        # Ensure geometry is valid and represents a polygon
        if geom.isGeosValid() and geom.type() == QgsWkbTypes.PolygonGeometry:
            if geom.isMultipart():
                polygons = geom.asMultiPolygon()
            else:
                polygons = [geom.asPolygon()]

            for polygon in polygons:
                for ring in polygon:
                    if not ring:
                        Logger.log(f"Feature ID {feature.id()} has an empty ring", level="WARNING")
                        continue  # skip empty rings

                    for i in range(len(ring) - 1):
                        try:
                            start_point = QgsPointXY(ring[i])
                            end_point = QgsPointXY(ring[i + 1])
                            edge_length = QgsPoint(start_point).distance(QgsPoint(end_point))

                            # Add edge info: feature ID, start point, end point, edge length
                            edges.append([
                                feature.id(),  # ID of the original building polygon
                                start_point.x(),
                                start_point.y(),
                                end_point.x(),
                                end_point.y(),
                                edge_length
                            ])
                        except Exception as e:
                            Logger.log(
                                f"Error processing edge for feature ID {feature.id()}: {str(e)}",
                                level="WARNING",
                            )
                            continue
        else:
            # Skip geometries that are not polygon type
            Logger.log(
                f"Invalid or unsupported geometry type for feature ID {feature.id()}",
                level="WARNING",
            )

    # Transform edges list into a dict keyed by feature ID
    hu_line_list_sorted = sorted(edges, key=itemgetter(0))
    hu_line_array = []
    sublist = []
    current_fid = hu_line_list_sorted[0][0]
    for row in hu_line_list_sorted:
        fid_orig = row[0]
        if fid_orig == current_fid:
            sublist.append(row[1:])
        else:
            hu_line_array.append([current_fid, sublist])
            sublist = [row[1:]]
        current_fid = fid_orig
    hu_line_array.append([current_fid, sublist])
    dict_hu = dict(list(hu_line_array))

    # Preserve original feature IDs as attributes before spatial join
    hu_layer.dataProvider().addAttributes([QgsField("fid_hu_orig", QMetaType.Int)])
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
    if debug_mode and workspace_path:
        save_debug_layer(hu_layer, _DEBUG_TOOL_NAME, "after_hu_fid_calc", workspace_path)

    mst_layer.dataProvider().addAttributes([QgsField("fid_mst_orig", QMetaType.Int)])
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
    if debug_mode and workspace_path:
        save_debug_layer(hu_points, _DEBUG_TOOL_NAME, "after_hu_centroids", workspace_path)

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
    if debug_mode and workspace_path:
        save_debug_layer(mst_layer_hu_join, _DEBUG_TOOL_NAME, "after_location_join", workspace_path)

    mst_list = []
    empty_polygon_layer = create_empty_layer("merge_layer_clustering_1", "Polygon", crs.authid())
    merge_layer_2 = create_empty_layer("merge_layer_clustering_2", "Polygon", crs.authid())

    for feature in mst_layer_hu_join.getFeatures():
        target_fid = feature["fid_mst_orig"]
        orig_fid = feature["fid_hu_orig"]
        mst_diff = feature["weight"]
        area = feature["Area"]
        mst_list.append([target_fid, orig_fid, mst_diff, area])

    orig_fid2 = 0
    area2 = 0
    mst_pair_list = []
    dict_fid_area = {}
    prev_target_fid = "x"
    list_outsorted = []

    mst_list_sorted = sorted(mst_list, key=itemgetter(0))

    for row in mst_list_sorted:
        target_fid, orig_fid1, mst_diff, area1 = row
        if target_fid == prev_target_fid:
            mst_pair_list.append([mst_diff, area1, area2, orig_fid1, orig_fid2])
        prev_target_fid = target_fid
        dict_fid_area[orig_fid1] = area1
        orig_fid2 = orig_fid1
        area2 = area1

    dict_member_group = {}
    dict_group_all_members = {}

    mst_pair_list_sorted = sorted(mst_pair_list, key=itemgetter(0))

    group_number = 0
    for element in mst_pair_list_sorted:
        mst_diff, area1, area2, orig_fid1, orig_fid2 = element
        group_status = False

        # Skip if either building ID is missing from the edge dictionary
        if orig_fid1 in dict_hu and orig_fid2 in dict_hu:
            pass
        else:
            Logger.log("fid in MST_Cluster missing", level="WARNING")
            continue

        # One building is already a member of a group
        if orig_fid1 in dict_member_group or orig_fid2 in dict_member_group:
            if orig_fid1 in dict_member_group:
                group_id = dict_member_group[orig_fid1]
                new_fid = orig_fid2
            else:
                group_id = dict_member_group[orig_fid2]
                new_fid = orig_fid1
            members_group = dict_group_all_members[group_id][:]
            members_group.extend([new_fid])
            members_coords = []

            for fid in members_group:
                members_coords.extend(dict_hu[fid])

            rect, area_rect = calc_bounding_rect(members_coords, empty_polygon_layer, "list", crs)
            sum_area = sum(dict_fid_area[fid] for fid in members_group)
            ratio = sum_area / area_rect * 100

            if ratio > overlap_ratio:
                dict_group_all_members[group_id] = members_group
                dict_member_group[new_fid] = group_id
                group_status = True
            else:
                list_outsorted.append(["G", orig_fid1, orig_fid2])

        if (orig_fid1 in dict_member_group or orig_fid2 in dict_member_group) is not True \
                or group_status is False:

            if orig_fid1 in dict_hu:
                coords1 = dict_hu[orig_fid1][:]
            else:
                Logger.log("Error in dict_hu:{} was not found".format(orig_fid1), level="CRITICAL")
                continue
            if orig_fid2 in dict_hu:
                coords2 = dict_hu[orig_fid2][:]
            else:
                Logger.log("Error in dict_hu:{} was not found".format(orig_fid2), level="CRITICAL")
                continue
            coords1.extend(coords2)

            rect, area_rect = calc_bounding_rect(coords1, empty_polygon_layer, "list", crs)
            ratio = (area1 + area2) / area_rect * 100

            if ratio > overlap_ratio:
                dict_member_group[orig_fid1] = group_number
                dict_member_group[orig_fid2] = group_number
                dict_group_all_members[group_number] = [orig_fid1, orig_fid2]
                group_number += 1
            else:
                list_outsorted.append(["S", orig_fid1, orig_fid2])

    rect_merge = None

    for group_key in dict_group_all_members:
        group_members = dict_group_all_members[group_key][:]
        members_coords = []
        for fid in group_members:
            members_coords.extend(dict_hu[fid])

        rect, area_rect = calc_bounding_rect(members_coords, empty_polygon_layer, "list", crs)

        try:
            rect_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [rect, merge_layer_2],
                'CRS': crs,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']
            merge_layer_2 = rect_merge
        except Exception as e:
            Logger.log(
                f"Group could not be merged: {group_members or 'None'} - {str(e)}",
                level="CRITICAL",
            )

    # Fallback return
    if not rect_merge:
        Logger.log("No valid rect_merge produced in mst_clustering", level="WARNING")
        rect_merge = merge_layer_2

    if debug_mode and workspace_path:
        save_debug_layer(rect_merge, _DEBUG_TOOL_NAME, "after_clustering", workspace_path)

    # TODO: remove features that are completely contained within another feature

    return rect_merge
