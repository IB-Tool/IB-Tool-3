# -*- coding: utf-8 -*-
"""
MST Utilities

Common utility functions for MST calculations.
"""

import math
from collections import defaultdict
from typing import List, Dict, Tuple, Any
from qgis.core import QgsVectorLayer, QgsField, edit
from qgis.PyQt.QtCore import QMetaType


class MSTUtilities:
    """Utility class for MST-related helper functions."""

    @staticmethod
    def unique_items(items: List[Any]) -> List[Any]:
        """
        Returns a list of unique elements.

        Args:
            items: List of items that can be converted to tuples

        Returns:
            List of unique items
        """
        return list(set(tuple(item) if isinstance(item, list) else item for item in items))

    @staticmethod
    def rounded_edge_key(x1: float, y1: float, x2: float, y2: float, precision: int = 0) -> Tuple[Tuple[float, float], Tuple[float, float]]:  # noqa: E501
        """
        Create a normalized, order-independent key for edge coordinates.

        Args:
            x1, y1: First point coordinates
            x2, y2: Second point coordinates
            precision: Decimal places for rounding

        Returns:
            Tuple of sorted coordinate pairs
        """
        p1 = (round(x1, precision), round(y1, precision))
        p2 = (round(x2, precision), round(y2, precision))
        return tuple(sorted([p1, p2]))

    @staticmethod
    def _build_grid(data_array, tolerance: float):
        """Index ``[x, y, value]`` rows by grid cell (cell size = *tolerance*).

        Args:
            data_array: List of ``[x, y, value]`` rows.
            tolerance: Cell size in map units.

        Returns:
            Dict ``(cell_x, cell_y) -> [row indices in array order]``.
        """
        inv_tol = 1.0 / tolerance
        grid = defaultdict(list)
        for i, (x, y, _node) in enumerate(data_array):
            grid[(math.floor(x * inv_tol), math.floor(y * inv_tol))].append(i)
        return grid

    @staticmethod
    def _first_match_index(grid, data_array, cx: float, cy: float, tolerance: float):
        """Return the lowest array index within *tolerance* of (cx, cy), or None.

        Args:
            grid: Dict ``(cell_x, cell_y) -> [array indices]`` with cell size = tolerance.
            data_array: List of ``[x, y, value]`` rows the grid was built from.
            cx: X coordinate of the query point (feature centroid).
            cy: Y coordinate of the query point.
            tolerance: Max. absolute difference per axis (exclusive).

        Returns:
            Index of the first matching row in array order (as the former
            nested loop), or ``None`` if no row matches.
        """
        inv_tol = 1.0 / tolerance
        gx, gy = math.floor(cx * inv_tol), math.floor(cy * inv_tol)
        best = None
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for i in grid.get((gx + dx, gy + dy), ()):
                    x, y, _node = data_array[i]
                    if abs(cx - x) < tolerance and abs(cy - y) < tolerance \
                            and (best is None or i < best):
                        best = i
        return best

    @staticmethod
    def join_array_to_polygons(
        layer: QgsVectorLayer,
        data_array: List[List[float]],
        field_name: str = "node",
        tolerance: float = 0.0001
    ) -> None:
        """
        Join data from array to polygon layer based on centroid coordinates.

        Args:
            layer: Building polygons layer
            data_array: List in format [[x, y, value], ...]
            field_name: Name of field to create/update
            tolerance: Coordinate comparison tolerance
        """
        # Add attribute field if not present
        field_names = [f.name() for f in layer.fields()]
        with edit(layer):
            if field_name not in field_names:
                layer.dataProvider().addAttributes([QgsField(field_name, QMetaType.QString)])
        layer.updateFields()
        field_index = layer.fields().indexFromName(field_name)

        # Grid index with cell size = tolerance: a match (|dx| < tol and |dy| < tol)
        # lies in a neighbouring cell. ±2 cells instead of ±1 absorb floating-point
        # error of the cell computation at large map coordinates. Replaces the
        # former nested loop over all array entries per feature (quadratic).
        grid = MSTUtilities._build_grid(data_array, tolerance)

        changes = {}
        for feature in layer.getFeatures():
            centroid = feature.geometry().centroid().asPoint()
            best = MSTUtilities._first_match_index(
                grid, data_array, centroid.x(), centroid.y(), tolerance)
            if best is not None:
                changes[feature.id()] = {field_index: str(data_array[best][2])}

        # Write all values at once (formerly one updateFeature per feature)
        with edit(layer):
            for fid, attributes in changes.items():
                layer.changeAttributeValues(fid, attributes)

    @staticmethod
    def polygon_support_points_dict(layer: QgsVectorLayer, field_name: str) -> Dict[str, List[Tuple[float, float]]]:
        """
        Create dictionary with field values as keys and polygon vertices as value lists.

        Args:
            layer: QgsVectorLayer with polygon geometry
            field_name: Name of field to use as dictionary key

        Returns:
            Dictionary {value: [(x1, y1), (x2, y2), ...]}
        """
        result_dict = {}

        for feature in layer.getFeatures():
            key = str(feature[field_name])
            geometry = feature.geometry()

            # Handle multipart polygons
            if geometry.isMultipart():
                polygons = geometry.asMultiPolygon()
            else:
                polygons = [geometry.asPolygon()]

            # Extract all vertices from all rings in all polygon parts
            vertices = []
            for polygon_part in polygons:
                for ring in polygon_part:
                    for pt in ring:
                        vertices.append((pt.x(), pt.y()))

            result_dict[key] = vertices

        return result_dict
