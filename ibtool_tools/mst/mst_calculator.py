# -*- coding: utf-8 -*-
"""
MST Calculator

Performs MST calculations and graph operations.
"""

from typing import List, Dict
import networkx as nx
import numpy as np
import scipy.spatial.distance as spd

from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem

from .mst_data_classes import EdgeData, MSTResult
from ...helpers.mst_utils import MSTUtilities
from ...helpers.geometry_utils import create_linestring_layer_from_array
from ...helpers.logger import Logger


class MSTCalculator:
    """Handles MST calculation and graph operations."""
    
    # MST calculation parameters
    COORDINATE_TOLERANCE = 0.0001
    """Tolerance for coordinate comparison in polygon joining"""
    
    def __init__(self):
        """Initialize the MST calculator."""
        self.logger = Logger()
    
    def build_graph_from_delaunay_list(
        self, 
        delaunay_list: List, 
        building_layer: QgsVectorLayer,
        point_node_mapping: List
    ) -> nx.Graph:
        """
        Build NetworkX graph from Delaunay edge list and building polygons.
        
        Args:
            delaunay_list: List of Delaunay edges in format [edge_str, x1, y1, x2, y2]
            building_layer: Building polygons layer with node field
            point_node_mapping: Mapping of points to node IDs
            
        Returns:
            NetworkX Graph object
        """
        # Join node information to building polygons
        MSTUtilities.join_array_to_polygons(
            building_layer, 
            point_node_mapping, 
            "node", 
            self.COORDINATE_TOLERANCE
        )
        
        # Create dictionary of polygon support points
        node_points_dict = MSTUtilities.polygon_support_points_dict(
            building_layer, 
            "node"
        )
        
        # Build graph
        graph = nx.Graph()
        
        for entry in delaunay_list:
            edge_str = entry[0]
            
            # Parse node IDs from edge string
            clean_str = edge_str.replace("[", "").replace("]", "").replace(" ", "")
            node1, node2 = clean_str.split(",", 1)
            
            # Get polygon support points for each node
            points_a = node_points_dict.get(node1, [])
            points_b = node_points_dict.get(node2, [])
            
            if points_a and points_b:
                # Calculate minimum distance between polygon boundaries
                distances = spd.cdist(points_a, points_b, metric='euclidean')
                weight = distances.min()
                
                # Add edge to graph
                graph.add_edge(node1, node2, weight=weight)

        return graph
    
    def calculate_minimum_spanning_tree(self, graph: nx.Graph) -> List[EdgeData]:
        """
        Calculate minimum spanning tree from graph.
        
        Args:
            graph: NetworkX Graph object
            
        Returns:
            List of EdgeData objects representing MST edges
        """
        if graph.number_of_nodes() == 0:
            self.logger.log("Empty graph provided for MST calculation", level="WARNING")
            return []
        
        # Calculate MST
        mst_edges_generator = nx.minimum_spanning_edges(graph, data=True)
        mst_edges_list = list(mst_edges_generator)
        
        # Convert to EdgeData objects
        mst_edges = []
        total_weight = 0.0
        
        for node1, node2, weight_data in mst_edges_list:
            weight = weight_data['weight']
            total_weight += weight
            
            # Note: We don't have exact coordinates here, they will be filled later
            edge = EdgeData(
                start_point=(0.0, 0.0),  # Placeholder
                end_point=(0.0, 0.0),    # Placeholder
                weight=weight,
                node1_id=node1,
                node2_id=node2
            )
            mst_edges.append(edge)

        return mst_edges
    
    def create_mst_layer_from_edges(
        self, 
        mst_edges: List[EdgeData], 
        points_array: np.ndarray,
        crs: QgsCoordinateReferenceSystem
    ) -> QgsVectorLayer:
        """
        Create QGIS layer from MST edges with actual coordinates.
        
        Args:
            mst_edges: List of MST EdgeData objects
            points_array: Array of point coordinates indexed by node ID
            crs: Coordinate reference system
            
        Returns:
            QgsVectorLayer containing MST lines
        """
        # Convert MST edges to array format for layer creation
        array_of_lines = []
        
        for edge in mst_edges:
            try:
                # Get coordinates from points array using node IDs
                node1_idx = int(edge.node1_id)
                node2_idx = int(edge.node2_id)
                
                x1, y1 = points_array[node1_idx]
                x2, y2 = points_array[node2_idx]
                
                # Update edge coordinates
                edge.start_point = (float(x1), float(y1))
                edge.end_point = (float(x2), float(y2))
                
                # Add to array format
                array_of_lines.append([
                    [x1, y1], 
                    [x2, y2], 
                    edge.weight
                ])
                
            except (ValueError, IndexError) as e:
                self.logger.log(
                    f"Error processing MST edge {edge.node1_id}-{edge.node2_id}: {e}", 
                    level="WARNING"
                )
                continue
        
        # Create layer using helper function
        layer_name = "mst_result"
        mst_layer = create_linestring_layer_from_array(array_of_lines, crs, layer_name)

        return mst_layer
    
    def calculate_mst_complete(
        self, 
        delaunay_list: List, 
        building_layer: QgsVectorLayer,
        point_node_mapping: List,
        points_array: np.ndarray,
        crs: QgsCoordinateReferenceSystem
    ) -> MSTResult:
        """
        Complete MST calculation workflow.
        
        Args:
            delaunay_list: Delaunay edge list
            building_layer: Building polygons layer
            point_node_mapping: Point to node mapping
            points_array: Array of point coordinates
            crs: Coordinate reference system
            
        Returns:
            MSTResult with complete MST data
        """
        # Build graph
        graph = self.build_graph_from_delaunay_list(
            delaunay_list, 
            building_layer, 
            point_node_mapping
        )
        
        # Calculate MST
        mst_edges = self.calculate_minimum_spanning_tree(graph)
        
        if not mst_edges:
            # Return empty result
            return MSTResult(
                mst_layer=None,
                edges=[],
                total_weight=0.0,
                node_count=0,
                edge_count=0,
                crs=crs
            )
        
        # Create layer
        mst_layer = self.create_mst_layer_from_edges(mst_edges, points_array, crs)
        
        # Calculate total weight
        total_weight = sum(edge.weight for edge in mst_edges)
        
        return MSTResult(
            mst_layer=mst_layer,
            edges=mst_edges,
            total_weight=total_weight,
            node_count=graph.number_of_nodes(),
            edge_count=len(mst_edges),
            crs=crs
        )