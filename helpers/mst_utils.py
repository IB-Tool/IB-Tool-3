# -*- coding: utf-8 -*-
"""
MST Utilities

Common utility functions for MST calculations.
"""

from typing import List, Dict, Tuple, Any
from qgis.core import QgsVectorLayer, QgsField, edit, QgsPointXY
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
    def rounded_edge_key(x1: float, y1: float, x2: float, y2: float, precision: int = 0) -> Tuple[Tuple[float, float], Tuple[float, float]]:
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
        
        # Update features
        with edit(layer):
            for feature in layer.getFeatures():
                centroid = feature.geometry().centroid().asPoint()
                for x, y, node in data_array:
                    if abs(centroid.x() - x) < tolerance and abs(centroid.y() - y) < tolerance:
                        feature[field_name] = str(node)
                        layer.updateFeature(feature)
                        break
    
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