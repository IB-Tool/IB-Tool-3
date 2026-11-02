# -*- coding: utf-8 -*-
"""Filter rules for the orthogonal projection lines of EdgeCatch.

Each building yields four orthogonal lines to the nearest roads (one per
rectangle edge direction). :func:`apply_filter_rules` reduces each group of
four to the plausible ones (max distance, endpoint inside the start
rectangle, parallel duplicates, all-parallel, angle outliers).

Moved unchanged from ``helpers/edge_catch_utils.py`` (module size).

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import math
from typing import List, Optional, Tuple

from qgis.core import QgsVectorLayer


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
    features_to_add = _filter_ortho_items(
        [(line, [line['x1'], line['y1'], line['x2'], line['y2'], line['angle'], line['distance']])
         for line in all_lines], min_lines_to_keep)

    if features_to_add:
        provider.addFeatures(features_to_add)

    filtered_layer.updateExtents()

    return filtered_layer


def _filter_ortho_items(items: list, min_lines_to_keep: int = 2) -> list:
    """Core of :func:`filter_ortho_lines` on plain lists.

    Args:
        items: ``(payload, [x1, y1, x2, y2, angle, distance, ...])`` per line, in
            order; lines of one building come in groups of 4.
        min_lines_to_keep: Minimum number of lines to keep per group.

    Returns:
        The payloads of the kept lines, in order.
    """
    kept = []
    for i in range(0, len(items), 4):
        group = items[i:min(i + 4, len(items))]
        if len(group) <= min_lines_to_keep:
            kept.extend(payload for payload, _attrs in group)
            continue
        line_data = [{
            'feature': payload,
            'distance': float(attrs[5]),
            'angle': float(attrs[4]),
            'x1': float(attrs[0]),
            'y1': float(attrs[1]),
            'x2': float(attrs[2]),
            'y2': float(attrs[3]),
        } for payload, attrs in group]
        kept.extend(line_info['feature'] for line_info in apply_filter_rules(line_data, min_lines_to_keep))
    return kept


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
