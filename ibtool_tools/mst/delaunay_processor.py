# -*- coding: utf-8 -*-
"""
Delaunay Processor

Handles Delaunay triangulation and geometric operations for MST calculations.
"""

from typing import List, Tuple, Set
import numpy as np
from scipy.spatial import Delaunay

from qgis.core import (
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsProcessing
)
from qgis.PyQt.QtCore import QMetaType
from qgis import processing

from .mst_data_classes import (
    EdgeData, TriangulationResult, BuildingCentroidsResult
)
from ...helpers.mst_utils import MSTUtilities
from ...helpers.logger import Logger


class DelaunayProcessor:
    """Handles Delaunay triangulation and related geometric operations."""
    
    def __init__(self):
        """Initialize the Delaunay processor."""
        self.logger = Logger()
        
    def extract_building_centroids(self, building_layer: QgsVectorLayer) -> BuildingCentroidsResult:
        """
        Extract centroids from building polygons.
        
        Args:
            building_layer: QgsVectorLayer containing building polygons
            
        Returns:
            BuildingCentroidsResult with centroid data
        """
        centroids = []
        building_count = 0
        
        for feature in building_layer.getFeatures():
            geom = feature.geometry()
            building_count += 1
            
            if geom.isMultipart():
                # Handle multipart polygons
                polygons = geom.asMultiPolygon()
                for polygon in polygons:
                    centroid = QgsGeometry.fromPolygonXY(polygon).centroid().asPoint()
                    centroids.append((centroid.x(), centroid.y()))
            else:
                # Handle single polygons
                centroid = geom.centroid().asPoint()
                centroids.append((centroid.x(), centroid.y()))
        
        points_array = np.array(centroids)
        
        self.logger.log(
            f"Extracted {len(centroids)} centroids from {building_count} buildings", 
            level="INFO"
        )
        
        return BuildingCentroidsResult(
            centroids=centroids,
            points_array=points_array,
            building_count=building_count
        )
    
    def create_triangulation(self, centroids_result: BuildingCentroidsResult) -> List[EdgeData]:
        """
        Create Delaunay triangulation from building centroids.
        
        Args:
            centroids_result: Result from extract_building_centroids
            
        Returns:
            List of EdgeData objects representing triangulation edges
        """
        points_array = centroids_result.points_array
        
        # Perform Delaunay triangulation
        tri = Delaunay(points_array)
        
        edges = []
        for simplex in tri.simplices:
            # Create edges from each triangle (3 edges per triangle)
            for i in range(3):
                p1_idx = simplex[i]
                p2_idx = simplex[(i + 1) % 3]
                
                point1 = points_array[p1_idx]
                point2 = points_array[p2_idx]
                
                # Calculate distance
                distance = np.linalg.norm(point1 - point2)
                
                edge = EdgeData(
                    start_point=(float(point1[0]), float(point1[1])),
                    end_point=(float(point2[0]), float(point2[1])),
                    weight=distance,
                    node1_id=str(p1_idx),
                    node2_id=str(p2_idx)
                )
                edges.append(edge)
        
        self.logger.log(f"Created {len(edges)} triangulation edges", level="INFO")
        return edges
    
    def create_triangulation_layer(
        self, 
        edges: List[EdgeData], 
        crs: 'QgsCoordinateReferenceSystem'
    ) -> QgsVectorLayer:
        """
        Create a QGIS layer from triangulation edges.
        
        Args:
            edges: List of EdgeData objects
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer containing triangulation lines
        """
        layer = QgsVectorLayer(
            f"LineString?crs={crs.toWkt()}", 
            f"{self.config.temp_layer_prefix}_triangulation", 
            "memory"
        )
        
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("weight", QMetaType.Double),
            QgsField("node1", QMetaType.QString),
            QgsField("node2", QMetaType.QString)
        ])
        layer.updateFields()
        
        features = []
        for edge in edges:
            x1, y1 = edge.start_point
            x2, y2 = edge.end_point
            
            geom = QgsGeometry.fromPolylineXY([
                QgsPointXY(x1, y1), 
                QgsPointXY(x2, y2)
            ])
            
            feature = QgsFeature()
            feature.setGeometry(geom)
            feature.setAttributes([
                edge.weight,
                edge.node1_id or "",
                edge.node2_id or ""
            ])
            features.append(feature)
        
        provider.addFeatures(features)
        return layer
    
    def filter_edges_by_streets(
        self, 
        triangulation_layer: QgsVectorLayer, 
        streets_layer: QgsVectorLayer
    ) -> List[EdgeData]:
        """
        Filter triangulation edges by removing those that intersect with streets.
        
        Args:
            triangulation_layer: Layer containing triangulation edges
            streets_layer: Layer containing street network
            
        Returns:
            List of filtered EdgeData objects
        """
        # Select triangulation edges that intersect with streets
        selection_result = processing.run("native:selectbylocation", {
            'INPUT': triangulation_layer,
            'PREDICATE': [0],  # intersects
            'INTERSECT': streets_layer,
            'METHOD': 0,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })
        
        # Remove selected (intersecting) edges from triangulation layer
        selected_ids = triangulation_layer.selectedFeatureIds()
        triangulation_layer.dataProvider().deleteFeatures(selected_ids)
        
        # Create edge index from remaining edges
        remaining_edges = self._create_edge_index_from_layer(triangulation_layer)
        
        self.logger.log(
            f"Filtered edges: {len(remaining_edges)} remaining after street filtering", 
            level="INFO"
        )
        
        return remaining_edges
    
    def create_delaunay_list_with_nodes(
        self, 
        triangulation_edges: List[EdgeData], 
        points_array: np.ndarray, 
        tri: Delaunay
    ) -> Tuple[List, List]:
        """
        Create Delaunay edge list with node information for MST processing.
        
        Args:
            triangulation_edges: Filtered triangulation edges
            points_array: Array of point coordinates
            tri: Delaunay triangulation object
            
        Returns:
            Tuple of (DelaunayList, ListOfPointsAndNodes)
        """
        delaunay_list = []
        list_of_points_and_nodes = []
        
        # Create edge index for fast lookup
        edge_index = set()
        for edge in triangulation_edges:
            key = MSTUtilities.rounded_edge_key(
                edge.start_point[0], edge.start_point[1],
                edge.end_point[0], edge.end_point[1],
                self.config.coordinate_precision
            )
            edge_index.add(key)
        
        # Process triangulation simplices
        for simplex_idx, simplex in enumerate(tri.simplices):
            for i in range(3):
                node1_idx = simplex[i]
                node2_idx = simplex[(i + 1) % 3]
                
                x1, y1 = points_array[node1_idx]
                x2, y2 = points_array[node2_idx]
                
                # Check if edge exists in filtered set
                key = MSTUtilities.rounded_edge_key(x1, y1, x2, y2, self.config.coordinate_precision)
                if key in edge_index:
                    # Ensure consistent node ordering
                    if node1_idx < node2_idx:
                        edge_str = f"[{node1_idx}, {node2_idx}]"
                        delaunay_list.append([edge_str, x1, y1, x2, y2])
                    else:
                        edge_str = f"[{node2_idx}, {node1_idx}]"
                        delaunay_list.append([edge_str, x2, y2, x1, y1])
            
            # Add point-node mappings
            for i in range(3):
                node_idx = simplex[i]
                x, y = points_array[node_idx]
                list_of_points_and_nodes.append([float(x), float(y), int(node_idx)])
        
        self.logger.log(f"Created Delaunay list with {len(delaunay_list)} edges", level="INFO")
        
        return delaunay_list, list_of_points_and_nodes
    
    def _create_edge_index_from_layer(self, layer: QgsVectorLayer) -> List[EdgeData]:
        """
        Create EdgeData list from QGIS layer features.
        
        Args:
            layer: QgsVectorLayer containing line features
            
        Returns:
            List of EdgeData objects
        """
        edges = []
        
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom.isMultipart():
                lines = geom.asMultiPolyline()
            else:
                lines = [geom.asPolyline()]
            
            for line in lines:
                if len(line) >= 2:
                    start = line[0]
                    end = line[-1]
                    
                    # Get weight from feature attributes if available
                    weight = feature.attribute('weight') or 0.0
                    node1 = feature.attribute('node1') or ""
                    node2 = feature.attribute('node2') or ""
                    
                    edge = EdgeData(
                        start_point=(start.x(), start.y()),
                        end_point=(end.x(), end.y()),
                        weight=weight,
                        node1_id=node1,
                        node2_id=node2
                    )
                    edges.append(edge)
        
        return edges