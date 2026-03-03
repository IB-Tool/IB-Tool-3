import math
from collections import defaultdict
from typing import List, Optional, Tuple

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsProcessing,
)
from qgis.PyQt.QtCore import QVariant

from .geometry_utils import shp_area2
from .logger import Logger
from .debug_utils import save_debug_layer
from .safe_processing import safe_processing_run


# ── EdgeCatch algorithm constants ─────────────────────────────────────────────
DEBUG_TOOL_NAME = "05_EdgeCatch"   # Sub-folder name for debug output files

ROAD_SEGMENT_LENGTH = 20    # Maximum segment length for road splitting (meters)
ROAD_BUFFER_DISTANCE = 25   # Buffer radius for building-proximity check (meters)
LINE_EXTEND_DISTANCE = 1    # Distance by which lines are extended before polygonizing (meters)
AREA_FILTER_FACTOR = 2      # Candidate polygons larger than source_area × factor are discarded

# Filter rule thresholds
_MAX_LINE_DISTANCE = 70         # Absolute maximum line distance (meters)
_ANGLE_SIMILARITY = 2           # Maximum angle difference to consider lines parallel (degrees)
_ALL_PARALLEL_THRESHOLD = 5     # Angle spread to classify all 4 lines as parallel (degrees)
_ENDPOINT_PROXIMITY = 5         # Maximum endpoint distance for parallel-line deduplication (meters)
_ANGLE_OUTLIER_DISTANCE_RATIO = 2.0   # Group with avg_dist > ratio × second-largest is removed


def _group_lines_by_angle(lines: list, angle_threshold: float) -> list:
    """Group lines with similar angles into clusters.

    Lines are sorted by angle and adjacent lines whose angle difference
    is within ``angle_threshold`` degrees are placed in the same group.

    Args:
        lines: List of line dicts, each containing an 'angle' key.
        angle_threshold: Maximum angle difference (degrees) for grouping.

    Returns:
        List of groups, where each group is a list of line dicts.
    """
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda x: x['angle'])
    groups = [[sorted_lines[0]]]

    for line in sorted_lines[1:]:
        if abs(line['angle'] - groups[-1][-1]['angle']) <= angle_threshold:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def _apply_rule_max_distance(line_data: list) -> list:
    """Rule 1 — discard lines exceeding the absolute maximum distance.

    Args:
        line_data: List of line dicts with a 'distance' key.

    Returns:
        Filtered list containing only lines within ``_MAX_LINE_DISTANCE``.
    """
    return [line for line in line_data if line['distance'] < _MAX_LINE_DISTANCE]


def _apply_rule_endpoint_in_rectangle(
    filtered: list, min_lines_to_keep: int
) -> list:
    """Rule 2 — remove lines whose endpoint falls inside the bounding rectangle
    of all start points (i.e., they point back into the building).

    Args:
        filtered: Current filtered line list.
        min_lines_to_keep: Minimum number of lines to retain.

    Returns:
        Filtered list after applying the rectangle rule.
    """
    def _point_in_rectangle(point: Tuple[float, float],
                            corners: List[Tuple[float, float]]) -> bool:
        x, y = point
        min_x = min(c[0] for c in corners)
        max_x = max(c[0] for c in corners)
        min_y = min(c[1] for c in corners)
        max_y = max(c[1] for c in corners)
        tolerance = 0.001
        return (min_x - tolerance <= x <= max_x + tolerance
                and min_y - tolerance <= y <= max_y + tolerance)

    start_points = [(line['x1'], line['y1']) for line in filtered]
    lines_to_keep = []
    lines_removed = []

    for line in filtered:
        end_point = (line['x2'], line['y2'])
        if _point_in_rectangle(end_point, start_points):
            lines_removed.append(line)
        else:
            lines_to_keep.append(line)

    if len(lines_to_keep) >= min_lines_to_keep:
        return lines_to_keep

    lines_removed.sort(key=lambda x: x['distance'])
    needed = min_lines_to_keep - len(lines_to_keep)
    return lines_to_keep + lines_removed[:needed]


def _apply_rule_parallel_close_endpoints(
    filtered: list, min_lines_to_keep: int
) -> list:
    """Rule 3a — for parallel line pairs with nearby endpoints, keep the shorter.

    Compares all pairs. If two lines have nearly the same angle (or opposite
    directions) and their endpoints are within ``_ENDPOINT_PROXIMITY`` meters,
    the longer one is removed.

    Args:
        filtered: Current filtered line list.
        min_lines_to_keep: Minimum number of lines to retain.

    Returns:
        Filtered list after applying the parallel/endpoint rule.
    """
    lines_to_remove = set()

    for i in range(len(filtered)):
        for j in range(i + 1, len(filtered)):
            line1 = filtered[i]
            line2 = filtered[j]

            angle_diff = abs(line1['angle'] - line2['angle'])
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            opposite_angle_diff = abs(abs(line1['angle'] - line2['angle']) - 180)
            if opposite_angle_diff > 180:
                opposite_angle_diff = 360 - opposite_angle_diff

            final_angle_diff = min(angle_diff, opposite_angle_diff)

            if final_angle_diff <= _ANGLE_SIMILARITY:
                endpoint_dist = math.sqrt(
                    (line1['x2'] - line2['x2']) ** 2
                    + (line1['y2'] - line2['y2']) ** 2
                )

                if endpoint_dist <= _ENDPOINT_PROXIMITY:
                    if line1['distance'] > line2['distance']:
                        lines_to_remove.add(i)
                    else:
                        lines_to_remove.add(j)

    if lines_to_remove and len(filtered) - len(lines_to_remove) >= min_lines_to_keep:
        return [line for idx, line in enumerate(filtered) if idx not in lines_to_remove]
    return filtered


def _apply_rule_all_parallel(filtered: list) -> Optional[list]:
    """Rule 3b — if all 4 lines are parallel, keep only the 2 shortest.

    Only applies when exactly 4 lines remain.

    Args:
        filtered: Current filtered line list (must have exactly 4 entries).

    Returns:
        The 2 shortest lines if all 4 are parallel, otherwise None (rule not
        applicable).
    """
    if len(filtered) != 4:
        return None

    angles = [line['angle'] for line in filtered]
    normalized_angles = [angle % 180 for angle in angles]
    if max(normalized_angles) - min(normalized_angles) <= _ALL_PARALLEL_THRESHOLD:
        filtered.sort(key=lambda x: x['distance'])
        return filtered[:2]

    return None


def _apply_rule_angle_outliers(filtered: list, min_lines_to_keep: int) -> list:
    """Rule 4 — remove the angle group with the largest average distance.

    Requires at least 3 angle groups. The group whose average distance is more
    than ``_ANGLE_OUTLIER_DISTANCE_RATIO`` times the second-largest average
    is discarded, provided enough lines remain afterward.

    Args:
        filtered: Current filtered line list.
        min_lines_to_keep: Minimum number of lines to retain.

    Returns:
        Filtered list after applying the angle-outlier rule.
    """
    if len(filtered) <= 2:
        return filtered

    grouped_angle = _group_lines_by_angle(filtered, _ANGLE_SIMILARITY)

    if len(grouped_angle) <= 1:
        return filtered

    group_stats = []
    for i, group in enumerate(grouped_angle):
        avg_distance = sum(line['distance'] for line in group) / len(group)
        group_stats.append((i, avg_distance, group))

    group_stats.sort(key=lambda x: x[1], reverse=True)

    max_distance = group_stats[0][1]
    second_max_distance = group_stats[1][1] if len(group_stats) > 1 else 0

    remaining_lines = sum(len(group) for _, _, group in group_stats[1:])

    if (remaining_lines >= min_lines_to_keep
            and max_distance > _ANGLE_OUTLIER_DISTANCE_RATIO * second_max_distance
            and len(grouped_angle) >= 3):
        result = []
        for _, _, group in group_stats[1:]:
            result.extend(group)
        return result

    return filtered


def create_shortest_lines_to_roads(
    point_layer: QgsVectorLayer,
    line_layer: QgsVectorLayer,
    plugin_instance=None,
) -> Optional[QgsVectorLayer]:
    """Create the shortest connection line from each point to the nearest road segment.

    Args:
        point_layer: QgsVectorLayer containing the source points.
        line_layer: QgsVectorLayer containing road line geometries.
        plugin_instance: Optional plugin instance for legacy iface access.
            Unused in the core pipeline.

    Returns:
        Temporary QgsVectorLayer with the shortest connection lines, or None
        on validation failure.
    """
    if not point_layer or not line_layer:
        Logger.log("Point or line layer is missing!", level="CRITICAL")
        return None

    if not point_layer.isValid() or not line_layer.isValid():
        Logger.log("One of the input layers is invalid!", level="CRITICAL")
        return None

    if point_layer.geometryType() != QgsWkbTypes.PointGeometry:
        Logger.log("The first layer must be a point layer!", level="CRITICAL")
        return None

    if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        Logger.log("The second layer must be a line layer!", level="CRITICAL")
        return None

    fields = QgsFields()
    fields.append(QgsField("x1", QVariant.Double))
    fields.append(QgsField("y1", QVariant.Double))
    fields.append(QgsField("x2", QVariant.Double))
    fields.append(QgsField("y2", QVariant.Double))
    fields.append(QgsField("angle", QVariant.Double))
    fields.append(QgsField("distance", QVariant.Double))
    fields.append(QgsField("point_id", QVariant.Int))
    fields.append(QgsField("line_id", QVariant.Int))

    crs = point_layer.crs()
    temp_layer = QgsVectorLayer(
        f"LineString?crs={crs.authid()}",
        "shortest_connections",
        "memory"
    )

    temp_layer_data = temp_layer.dataProvider()
    temp_layer_data.addAttributes(fields)
    temp_layer.updateFields()

    new_features = []
    error_count = 0
    processed_count = 0

    line_features = list(line_layer.getFeatures())

    for point_feat in point_layer.getFeatures():
        point_geom = point_feat.geometry()

        if point_geom.isNull() or point_geom.isEmpty():
            error_count += 1
            Logger.log(
                f"Point feature {point_feat.id()} has no valid geometry.",
                level="WARNING",
            )
            continue

        point = point_geom.asPoint()

        min_distance = float('inf')
        closest_point = None
        closest_line_id = None

        for line_feat in line_features:
            line_geom = line_feat.geometry()

            if line_geom.isNull() or line_geom.isEmpty():
                continue

            closest_point_on_line = line_geom.nearestPoint(point_geom)

            if not closest_point_on_line.isNull():
                distance = point_geom.distance(closest_point_on_line)

                if distance < min_distance:
                    min_distance = distance
                    closest_point = closest_point_on_line.asPoint()
                    closest_line_id = line_feat.id()

        if closest_point:
            line_geom = QgsGeometry.fromPolylineXY([point, closest_point])

            dx = closest_point.x() - point.x()
            dy = closest_point.y() - point.y()
            angle_deg = math.degrees(math.atan2(dy, dx))
            if angle_deg < 0:
                angle_deg += 360

            feature = QgsFeature()
            feature.setGeometry(line_geom)
            feature.setAttributes([
                point.x(),
                point.y(),
                closest_point.x(),
                closest_point.y(),
                angle_deg,
                min_distance,
                point_feat.id(),
                closest_line_id,
            ])

            new_features.append(feature)
            processed_count += 1
        else:
            error_count += 1
            Logger.log(
                f"No nearest line found for point {point_feat.id()}.",
                level="WARNING",
            )

    temp_layer_data.addFeatures(new_features)

    status_msg = f"Created {processed_count} connection lines successfully."
    if error_count > 0:
        status_msg += f" {error_count} features could not be processed (see log)."
    Logger.log(status_msg, level="INFO")

    return temp_layer


def filter_ortho_lines(
    hu_ortho: QgsVectorLayer,
    min_lines_to_keep: int = 2,
) -> QgsVectorLayer:
    """Filter orthogonal projection lines by applying sequential filter rules.

    Groups lines from the same building (in groups of 4) and applies
    ``apply_filter_rules`` to each group.

    Args:
        hu_ortho: QgsVectorLayer containing orthogonal projection lines.
        min_lines_to_keep: Minimum number of lines to keep per group.

    Returns:
        QgsVectorLayer containing the filtered orthogonal lines.
    """
    filtered_layer = QgsVectorLayer(
        f"LineString?crs={hu_ortho.crs().authid()}",
        "filtered_ortho_lines",
        "memory"
    )

    provider = filtered_layer.dataProvider()
    provider.addAttributes(hu_ortho.fields())
    filtered_layer.updateFields()

    all_lines = list(hu_ortho.getFeatures())
    features_to_add = []

    for i in range(0, len(all_lines), 4):
        group = all_lines[i:min(i + 4, len(all_lines))]

        if len(group) <= min_lines_to_keep:
            features_to_add.extend(group)
            continue

        line_data = []
        for line in group:
            line_data.append({
                'feature': line,
                'distance': float(line['distance']),
                'angle': float(line['angle']),
                'x1': float(line['x1']),
                'y1': float(line['y1']),
                'x2': float(line['x2']),
                'y2': float(line['y2'])
            })

        filtered_lines = apply_filter_rules(line_data, min_lines_to_keep)

        for line_info in filtered_lines:
            features_to_add.append(line_info['feature'])

    if features_to_add:
        provider.addFeatures(features_to_add)

    filtered_layer.updateExtents()

    return filtered_layer


def apply_filter_rules(line_data: list, min_lines_to_keep: int) -> list:
    """Apply sequential filter rules to a group of orthogonal projection lines.

    Rules are applied in order; each rule may reduce the set. Processing stops
    early if the minimum number of lines is reached.

    Rule 1 — Absolute maximum distance (``_MAX_LINE_DISTANCE``).
    Rule 2 — Remove lines whose endpoint falls inside the start-point rectangle.
    Rule 3a — Remove the longer of two parallel lines with nearby endpoints.
    Rule 3b — If all 4 lines are parallel, keep only the 2 shortest.
    Rule 4 — Remove the angle group with the largest average distance.

    Args:
        line_data: List of line dicts with keys: distance, angle, x1, y1, x2, y2,
            feature.
        min_lines_to_keep: Minimum number of lines to retain.

    Returns:
        Filtered list of line dicts.
    """
    # Rule 1: Absolute maximum distance
    filtered = _apply_rule_max_distance(line_data)
    if not filtered or len(filtered) <= min_lines_to_keep:
        return filtered

    # Rule 2: Endpoint inside start-point rectangle
    filtered = _apply_rule_endpoint_in_rectangle(filtered, min_lines_to_keep)
    if len(filtered) <= min_lines_to_keep:
        return filtered

    # Rule 3a: Parallel lines with nearby endpoints — keep the shorter
    filtered = _apply_rule_parallel_close_endpoints(filtered, min_lines_to_keep)
    if len(filtered) <= min_lines_to_keep:
        return filtered

    # Rule 3b: All 4 lines parallel — keep only 2 shortest
    result_3b = _apply_rule_all_parallel(filtered)
    if result_3b is not None:
        return result_3b

    # Rule 4: Remove angle-group outlier with largest average distance
    filtered = _apply_rule_angle_outliers(filtered, min_lines_to_keep)

    return filtered


def project_point_to_line(
    point: QgsPointXY,
    line_geom: QgsGeometry,
) -> Tuple[Optional[QgsPointXY], float]:
    """Project a point onto a line geometry.

    Args:
        point: QgsPointXY to project.
        line_geom: QgsGeometry to project onto.

    Returns:
        Tuple of (projected QgsPointXY, distance). Returns (None, inf) on failure.
    """
    point_geom = QgsGeometry.fromPointXY(point)
    closest = line_geom.nearestPoint(point_geom)
    if closest.isNull():
        return None, float('inf')
    projected = closest.asPoint()
    distance = point_geom.distance(closest)
    return QgsPointXY(projected.x(), projected.y()), distance


def extract_road_subline(
    foot_point_a: QgsPointXY,
    foot_point_b: QgsPointXY,
    road_features,
) -> Optional[List[QgsPointXY]]:
    """Extract the intermediate road vertices between two foot points.

    Merges road geometries in the relevant area and extracts the sub-curve
    between ``foot_point_a`` and ``foot_point_b``. Robust against multi-feature
    segments and T-junctions.

    Args:
        foot_point_a: First foot point on the road (projection of edge_start).
        foot_point_b: Second foot point on the road (projection of edge_end).
        road_features: Road features (QgsVectorLayer or iterable of QgsFeature)
            in the relevant area.

    Returns:
        List of intermediate QgsPointXY vertices between the two foot points
        (excluding the foot points themselves). Returns an empty list for a
        straight road, or None on failure.
    """
    geom_list = []
    if hasattr(road_features, 'getFeatures'):
        features = road_features.getFeatures()
    else:
        features = road_features

    for feat in features:
        geom = feat.geometry()
        if not geom.isNull() and not geom.isEmpty():
            geom_list.append(geom)

    if not geom_list:
        Logger.log("extract_road_subline: No valid road geometries found.", level="WARNING")
        return None

    collected = QgsGeometry.collectGeometry(geom_list)
    merged = collected.mergeLines()

    point_a_geom = QgsGeometry.fromPointXY(foot_point_a)
    point_b_geom = QgsGeometry.fromPointXY(foot_point_b)

    if merged.isMultipart():
        best_line = None
        best_total_dist = float('inf')
        for part in merged.asGeometryCollection():
            if part.isNull() or part.isEmpty():
                continue
            dist_a = part.distance(point_a_geom)
            dist_b = part.distance(point_b_geom)
            total = dist_a + dist_b
            if total < best_total_dist:
                best_total_dist = total
                best_line = part
        if best_line is None:
            Logger.log("extract_road_subline: No matching line part found.", level="WARNING")
            return None
        merged = best_line

    dist_a = merged.lineLocatePoint(point_a_geom)
    dist_b = merged.lineLocatePoint(point_b_geom)

    reversed_order = dist_a > dist_b
    start_dist = min(dist_a, dist_b)
    end_dist = max(dist_a, dist_b)

    abstract_geom = merged.constGet()
    sub_curve = abstract_geom.curveSubstring(start_dist, end_dist)
    subline = QgsGeometry(sub_curve)

    if subline.isNull() or subline.isEmpty():
        Logger.log("extract_road_subline: curveSubstring returned empty geometry.", level="WARNING")
        return None

    all_vertices = [QgsPointXY(v.x(), v.y()) for v in subline.vertices()]

    # Strip the re-projected foot points (first and last vertex)
    intermediate = [] if len(all_vertices) <= 2 else all_vertices[1:-1]

    if reversed_order:
        intermediate.reverse()

    return intermediate


def build_catch_polygon(
    edge_start: QgsPointXY,
    edge_end: QgsPointXY,
    foot_a: QgsPointXY,
    foot_b: QgsPointXY,
    road_intermediate_vertices: Optional[List[QgsPointXY]] = None,
) -> Optional[QgsGeometry]:
    """Build a catch polygon from building edge vertices, foot points, and road vertices.

    The polygon ring follows:
    edge_start → edge_end → foot_b → [road vertices B→A] → foot_a → edge_start

    Args:
        edge_start: Start vertex of the building edge (on the bounding rectangle).
        edge_end: End vertex of the building edge (on the bounding rectangle).
        foot_a: Foot point on the road at edge_start (from orthogonal projection).
        foot_b: Foot point on the road at edge_end (from orthogonal projection).
        road_intermediate_vertices: Intermediate road vertices from foot_a to
            foot_b (excluding foot points). Pass None or [] for a straight road.

    Returns:
        QgsGeometry polygon, or None on failure.
    """
    if road_intermediate_vertices is None:
        road_intermediate_vertices = []

    points = [edge_start, edge_end, foot_b]
    points.extend(reversed(road_intermediate_vertices))
    points.append(foot_a)
    points.append(edge_start)

    if len(points) < 4:
        return None

    polygon = QgsGeometry.fromPolygonXY([points])

    if polygon.isNull() or polygon.isEmpty():
        Logger.log("build_catch_polygon: Created polygon is invalid.", level="WARNING")
        return None

    if not polygon.isGeosValid():
        polygon = polygon.makeValid()
        if polygon.isNull() or polygon.isEmpty():
            return None

    return polygon


def delete_first_point(layer: QgsVectorLayer) -> QgsVectorLayer:
    """Return a copy of the layer with its first feature removed.

    Args:
        layer: QgsVectorLayer to process.

    Returns:
        New QgsVectorLayer without the first feature. Returns the original
        layer unchanged if it has one or fewer features.
    """
    from qgis.core import QgsVectorLayer

    features = list(layer.getFeatures())
    if len(features) <= 1:
        return layer

    new_layer = QgsVectorLayer(
        f"{layer.geometryType().name}?crs={layer.crs().authid()}", "filtered",
        "memory")
    new_layer.dataProvider().addAttributes(layer.fields())
    new_layer.updateFields()

    new_layer.dataProvider().addFeatures(features[1:])

    return new_layer


# ── Road network preprocessing ────────────────────────────────────────────────

def _normalize_node(point: QgsPointXY) -> Tuple[float, float]:
    """Create a hashable node key with limited coordinate precision."""
    return (round(point.x(), 8), round(point.y(), 8))


def _build_minimized_lines_from_selection(
    road_network_sel: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
) -> QgsVectorLayer:
    """Reduce a selected road network to the minimum number of line features.

    Decomposes all polylines into vertex-to-vertex segments, removes duplicates,
    builds an adjacency graph, and reassembles the segments into chains running
    from one intersection/endpoint to the next. Straight sequences of degree-2
    nodes are merged into a single feature; closed rings with no dedicated
    endpoint are handled in a second pass.

    Args:
        road_network_sel: QgsVectorLayer — pre-selected road line layer.
        crs: QgsCoordinateReferenceSystem — CRS for the output layer.

    Returns:
        QgsVectorLayer — road lines reassembled as minimal chains.
    """
    if road_network_sel.featureCount() == 0:
        return road_network_sel

    unique_segments = {}
    adjacency = defaultdict(set)

    for feature in road_network_sel.getFeatures():
        geometry = feature.geometry()
        if not geometry or geometry.isEmpty():
            continue

        parts = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]

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

    def _traverse_chain(start_node, next_node):
        """Follow a chain of degree-2 nodes from start_node through next_node."""
        chain = [start_node, next_node]
        prev_node = start_node
        curr_node = next_node
        local_visited = {tuple(sorted([start_node, next_node]))}

        while len(adjacency[curr_node]) == 2:
            candidates = [node for node in adjacency[curr_node] if node != prev_node]
            if not candidates:
                break
            forward_node = candidates[0]
            segment = tuple(sorted([curr_node, forward_node]))
            if segment in visited_segments or segment in local_visited:
                break
            local_visited.add(segment)
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

            chain = _traverse_chain(start_node, neighbor)
            for a, b in zip(chain[:-1], chain[1:]):
                visited_segments.add(tuple(sorted([a, b])))

            new_feature = QgsFeature(result_layer.fields())
            new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
            new_feature["src_count"] = len(chain) - 1
            features_to_add.append(new_feature)

    # Handle closed rings that have no start/end node with degree != 2
    for segment in unique_segments:
        if segment in visited_segments:
            continue
        start_node, next_node = segment
        chain = _traverse_chain(start_node, next_node)
        for a, b in zip(chain[:-1], chain[1:]):
            visited_segments.add(tuple(sorted([a, b])))

        new_feature = QgsFeature(result_layer.fields())
        new_feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in chain]))
        new_feature["src_count"] = len(chain) - 1
        features_to_add.append(new_feature)

    result_provider.addFeatures(features_to_add)
    return result_layer


def filter_roads_near_buildings(
    road_network: QgsVectorLayer,
    hu_input: QgsVectorLayer,
    segment_length: float,
    buffer_distance: float,
    debug_mode: bool = False,
    workspace_path: Optional[str] = None,
) -> QgsVectorLayer:
    """Filter road segments to only those adjacent to building footprints.

    Splits the road network into segments of ``segment_length`` meters, stamps a
    stable ``seg_id`` attribute onto each segment, creates a symmetric buffer of
    ``buffer_distance`` around each segment, and retains only segments whose
    buffer intersects at least one building footprint. The match is done via
    the ``seg_id`` attribute (not spatial overlap of the segments themselves) so
    that neighbouring segments outside a qualifying buffer are never accidentally
    included.

    Debug checkpoint (when ``debug_mode`` is active):

    - ``road_segs_near_buildings`` — road segments whose buffer touches a building

    Args:
        road_network: QgsVectorLayer — input road line layer.
        hu_input: QgsVectorLayer — building footprints layer.
        segment_length: Maximum segment length in map units (meters).
        buffer_distance: Buffer radius in map units (meters) applied
            symmetrically on both sides of each road segment.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer — road segments that are adjacent to buildings.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)

    road_segs = safe_processing_run("native:splitlinesbylength", {
        'INPUT': road_network,
        'LENGTH': segment_length,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs = safe_processing_run("native:fieldcalculator", {
        'INPUT': road_segs,
        'FIELD_NAME': 'seg_id',
        'FIELD_TYPE': 1,
        'FIELD_LENGTH': 10,
        'FORMULA': '$id',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs_buf = safe_processing_run("native:buffer", {
        'INPUT': road_segs,
        'DISTANCE': buffer_distance,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    road_segs_buf_near_bdgs = safe_processing_run("native:extractbylocation", {
        'INPUT': road_segs_buf,
        'PREDICATE': [0],  # intersects
        'INTERSECT': hu_input,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    near_bdg_seg_ids = {f['seg_id'] for f in road_segs_buf_near_bdgs.getFeatures()}

    if not near_bdg_seg_ids:
        return road_segs_buf_near_bdgs

    id_list = ", ".join(str(sid) for sid in near_bdg_seg_ids)
    road_segs_near_bdgs = safe_processing_run("native:extractbyexpression", {
        'INPUT': road_segs,
        'EXPRESSION': f'"seg_id" IN ({id_list})',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    if debug_mode and workspace_path:
        save_debug_layer(road_segs_near_bdgs, DEBUG_TOOL_NAME, "road_segs_near_buildings", workspace_path)

    return road_segs_near_bdgs


def process_single_feature(
    feature: QgsFeature,
    road_network: QgsVectorLayer,
    bloecke: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    debug_mode: bool = False,
    workspace_path: Optional[str] = None,
) -> Optional[QgsVectorLayer]:
    """Run the edge-catch pipeline for one grouped building feature.

    Creates a temporary single-feature layer, projects the building outline onto
    the adjacent road network via orthogonal lines, polygonizes the combined line
    geometry, clips the result to the relevant city block, and returns only
    polygons no larger than ``AREA_FILTER_FACTOR`` times the source area.

    Args:
        feature: QgsFeature — a single grouped building polygon; must already
            have an ``Area`` attribute populated by ``shp_area2``.
        road_network: QgsVectorLayer — pre-filtered road segment layer.
        bloecke: QgsVectorLayer — city block polygon layer.
        crs: QgsCoordinateReferenceSystem — CRS used for all temporary layers.
        debug_mode: If True, saves intermediate results as numbered GeoPackages.
        workspace_path: Base path for debug output files.

    Returns:
        QgsVectorLayer with candidate polygons, or None if the feature is skipped.
    """
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name=DEBUG_TOOL_NAME)

    fid = feature.id()
    area = feature['Area']
    if area is None or area == 0:
        Logger.log(f"Feature {fid}: Area is None or 0, skipping", level="WARNING")
        return None

    temp_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", f"temp_feature_{fid}", "memory")
    temp_layer.dataProvider().addFeatures([QgsFeature(feature)])
    temp_layer = safe_processing_run("native:fixgeometries", {
        'INPUT': temp_layer,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    outline_points = safe_processing_run("native:extractvertices", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    outline_points = delete_first_point(outline_points)

    block_sel = safe_processing_run("native:extractbylocation", {
        'INPUT': bloecke,
        'PREDICATE': [0],  # intersects
        'INTERSECT': outline_points,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    road_network_sel = safe_processing_run("native:extractbylocation", {
        'INPUT': road_network,
        'PREDICATE': [0],  # intersects
        'INTERSECT': block_sel,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    road_network_sel = _build_minimized_lines_from_selection(road_network_sel, crs)

    hu_ortho = create_shortest_lines_to_roads(outline_points, road_network_sel)
    hu_ortho_filter = filter_ortho_lines(hu_ortho)

    group_outline = safe_processing_run("native:polygonstolines", {
        'INPUT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    group_outline_split = safe_processing_run("native:explodelines", {
        'INPUT': group_outline,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    lines_merged = safe_processing_run("native:mergevectorlayers", {
        'LAYERS': [road_network_sel, hu_ortho_filter, group_outline_split],
        'CRS': crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    lines_extended = safe_processing_run("native:extendlines", {
        'INPUT': lines_merged,
        'START_DISTANCE': LINE_EXTEND_DISTANCE,
        'END_DISTANCE': LINE_EXTEND_DISTANCE,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    lines_fixed = safe_processing_run("native:fixgeometries", {
        'INPUT': lines_extended,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    polygons = safe_processing_run("native:polygonize", {
        'INPUT': lines_fixed,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    polygons_in_feature = safe_processing_run("native:extractbylocation", {
        'INPUT': polygons,
        'PREDICATE': [0],  # intersects
        'INTERSECT': temp_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
    polygons_in_block = safe_processing_run("native:intersection", {
        'INPUT': polygons_in_feature,
        'OVERLAY': block_sel,
        'INPUT_FIELDS': [],
        'OVERLAY_FIELDS': [],
        'OVERLAY_FIELDS_PREFIX': '',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': None
    }, **_dbg)['OUTPUT']
    polygons_in_block = safe_processing_run("native:fixgeometries", {
        'INPUT': polygons_in_block,
        'METHOD': 1,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    shp_area2(polygons_in_block)
    polygons_small = safe_processing_run("native:extractbyexpression", {
        'INPUT': polygons_in_block,
        'EXPRESSION': f'"Area" < {area * AREA_FILTER_FACTOR}',  # TODO: verify operator direction
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']

    return polygons_small
