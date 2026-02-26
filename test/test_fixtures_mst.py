# -*- coding: utf-8 -*-
"""
Test fixtures for MST testing

Provides reusable test data and utilities for MST functionality tests.
"""

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField,
    QgsCoordinateReferenceSystem, QgsWkbTypes
)
from qgis.PyQt.QtCore import QMetaType, QVariant


class MSTTestFixtures:
    """Provides test fixtures for MST functionality testing."""

    @staticmethod
    def create_test_crs():
        """Create a standard CRS for testing."""
        return QgsCoordinateReferenceSystem("EPSG:3857")  # Web Mercator

    @staticmethod
    def create_simple_building_layer():
        """Create a simple building layer with 4 rectangular buildings."""
        crs = MSTTestFixtures.create_test_crs()
        layer = QgsVectorLayer(f"Polygon?crs={crs.toWkt()}", "test_buildings", "memory")
        provider = layer.dataProvider()
        
        # Add standard fields
        provider.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("name", QVariant.String),
            QgsField("area", QVariant.Double)
        ])
        layer.updateFields()

        # Create 4 simple rectangular buildings in a grid pattern
        buildings = [
            # Building 1: Bottom-left
            {
                'points': [
                    QgsPointXY(0, 0), QgsPointXY(10, 0), 
                    QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
                ],
                'id': 1, 'name': 'Building1', 'area': 100.0
            },
            # Building 2: Bottom-right  
            {
                'points': [
                    QgsPointXY(20, 0), QgsPointXY(30, 0),
                    QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)
                ],
                'id': 2, 'name': 'Building2', 'area': 100.0
            },
            # Building 3: Top-left
            {
                'points': [
                    QgsPointXY(0, 20), QgsPointXY(10, 20),
                    QgsPointXY(10, 30), QgsPointXY(0, 30), QgsPointXY(0, 20)
                ],
                'id': 3, 'name': 'Building3', 'area': 100.0
            },
            # Building 4: Top-right
            {
                'points': [
                    QgsPointXY(20, 20), QgsPointXY(30, 20),
                    QgsPointXY(30, 30), QgsPointXY(20, 30), QgsPointXY(20, 20)
                ],
                'id': 4, 'name': 'Building4', 'area': 100.0
            }
        ]

        features = []
        for building_data in buildings:
            feature = QgsFeature(layer.fields())
            geometry = QgsGeometry.fromPolygonXY([building_data['points']])
            feature.setGeometry(geometry)
            feature.setAttributes([
                building_data['id'],
                building_data['name'], 
                building_data['area']
            ])
            features.append(feature)

        provider.addFeatures(features)
        return layer

    @staticmethod
    def create_simple_street_layer():
        """Create a simple street network connecting building areas."""
        crs = MSTTestFixtures.create_test_crs()
        layer = QgsVectorLayer(f"LineString?crs={crs.toWkt()}", "test_streets", "memory")
        provider = layer.dataProvider()
        
        # Add standard fields
        provider.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("name", QVariant.String),
            QgsField("length", QVariant.Double)
        ])
        layer.updateFields()

        # Create street network
        streets = [
            # Horizontal street connecting buildings 1-2
            {
                'points': [QgsPointXY(10, 5), QgsPointXY(20, 5)],
                'id': 1, 'name': 'Street1', 'length': 10.0
            },
            # Vertical street connecting buildings 1-3
            {
                'points': [QgsPointXY(5, 10), QgsPointXY(5, 20)],
                'id': 2, 'name': 'Street2', 'length': 10.0
            },
            # Horizontal street connecting buildings 3-4
            {
                'points': [QgsPointXY(10, 25), QgsPointXY(20, 25)],
                'id': 3, 'name': 'Street3', 'length': 10.0
            },
            # Vertical street connecting buildings 2-4
            {
                'points': [QgsPointXY(25, 10), QgsPointXY(25, 20)],
                'id': 4, 'name': 'Street4', 'length': 10.0
            },
            # Long diagonal street (should be filtered out with road_length=50)
            {
                'points': [QgsPointXY(-10, -10), QgsPointXY(40, 40)],
                'id': 5, 'name': 'LongStreet', 'length': 70.7
            }
        ]

        features = []
        for street_data in streets:
            feature = QgsFeature(layer.fields())
            geometry = QgsGeometry.fromPolylineXY(street_data['points'])
            feature.setGeometry(geometry)
            feature.setAttributes([
                street_data['id'],
                street_data['name'],
                street_data['length']
            ])
            features.append(feature)

        provider.addFeatures(features)
        return layer

    @staticmethod  
    def create_complex_building_layer():
        """Create a more complex building layer for advanced testing."""
        crs = MSTTestFixtures.create_test_crs()
        layer = QgsVectorLayer(f"Polygon?crs={crs.toWkt()}", "complex_buildings", "memory")
        provider = layer.dataProvider()
        
        provider.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("name", QVariant.String),
            QgsField("area", QVariant.Double),
            QgsField("type", QVariant.String)
        ])
        layer.updateFields()

        # Create various building shapes and sizes
        buildings = [
            # Small square building
            {
                'points': [
                    QgsPointXY(0, 0), QgsPointXY(5, 0),
                    QgsPointXY(5, 5), QgsPointXY(0, 5), QgsPointXY(0, 0)
                ],
                'id': 1, 'name': 'SmallBuilding', 'area': 25.0, 'type': 'residential'
            },
            # Large rectangular building
            {
                'points': [
                    QgsPointXY(10, 0), QgsPointXY(25, 0),
                    QgsPointXY(25, 20), QgsPointXY(10, 20), QgsPointXY(10, 0)
                ],
                'id': 2, 'name': 'LargeBuilding', 'area': 300.0, 'type': 'commercial'
            },
            # L-shaped building
            {
                'points': [
                    QgsPointXY(30, 0), QgsPointXY(40, 0), QgsPointXY(40, 10),
                    QgsPointXY(35, 10), QgsPointXY(35, 15), QgsPointXY(30, 15),
                    QgsPointXY(30, 0)
                ],
                'id': 3, 'name': 'LBuilding', 'area': 150.0, 'type': 'mixed'
            },
            # Isolated building (far from others)
            {
                'points': [
                    QgsPointXY(100, 100), QgsPointXY(110, 100),
                    QgsPointXY(110, 110), QgsPointXY(100, 110), QgsPointXY(100, 100)
                ],
                'id': 4, 'name': 'IsolatedBuilding', 'area': 100.0, 'type': 'industrial'
            }
        ]

        features = []
        for building_data in buildings:
            feature = QgsFeature(layer.fields())
            geometry = QgsGeometry.fromPolygonXY([building_data['points']])
            feature.setGeometry(geometry)
            feature.setAttributes([
                building_data['id'],
                building_data['name'],
                building_data['area'],
                building_data['type']
            ])
            features.append(feature)

        provider.addFeatures(features)
        return layer

    @staticmethod
    def create_empty_layer(layer_type="Polygon"):
        """Create an empty layer for error testing."""
        crs = MSTTestFixtures.create_test_crs()
        layer = QgsVectorLayer(f"{layer_type}?crs={crs.toWkt()}", "empty_layer", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int)])
        layer.updateFields()
        return layer

    @staticmethod
    def get_expected_mst_edges():
        """Return expected MST edges for simple building layout."""
        # For the simple 4-building grid, MST should connect them with minimum total distance
        # Expected connections based on centroids at (5,5), (25,5), (5,25), (25,25)
        return [
            # Building1 to Building2: distance 20
            {'from': (5, 5), 'to': (25, 5), 'weight': 20.0},
            # Building1 to Building3: distance 20  
            {'from': (5, 5), 'to': (5, 25), 'weight': 20.0},
            # Building2 to Building4: distance 20
            {'from': (25, 5), 'to': (25, 25), 'weight': 20.0}
        ]

    @staticmethod
    def validate_mst_layer(mst_layer):
        """Validate that an MST layer has expected properties."""
        if not mst_layer or not mst_layer.isValid():
            return False, "Layer is None or invalid"
            
        if mst_layer.wkbType() != QgsWkbTypes.LineString:
            return False, f"Expected LineString, got {mst_layer.wkbType()}"
            
        feature_count = mst_layer.featureCount()
        if feature_count == 0:
            return False, "Layer has no features"
            
        # For n buildings, MST should have n-1 edges
        # For simple case with 4 buildings, expect 3 edges
        expected_edges = 3
        if feature_count != expected_edges:
            return False, f"Expected {expected_edges} edges, got {feature_count}"
            
        return True, "Layer validation passed"