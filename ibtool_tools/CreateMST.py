# -*- coding: utf-8 -*-
"""
CreateMST - Refactored Version

Refactored MST calculation with improved structure, testability, and maintainability.
This replaces the original CreateMST.py with a clean, modular architecture.
"""

from typing import Optional
from scipy.spatial import Delaunay

from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem

from .mst import (
    DelaunayProcessor, StreetProcessor, MSTCalculator,
    MSTResult, TriangulationResult, StreetProcessingResult
)
from ..helpers.logger import Logger


class CreateMST:
    """
    Main orchestrator class for MST calculation.
    
    This class coordinates the different processing components to perform
    complete MST calculation workflow with clear separation of concerns.
    """
    
    def __init__(self):
        """Initialize MST calculator with components."""
        self.logger = Logger
        
        # Initialize processing components
        self.delaunay_processor = DelaunayProcessor()
        self.street_processor = StreetProcessor()
        self.mst_calculator = MSTCalculator()
    
    def calculate_mst(
        self, 
        input_buildings: QgsVectorLayer,
        streets_original: QgsVectorLayer, 
        spatial_reference: QgsCoordinateReferenceSystem
    ) -> Optional[QgsVectorLayer]:
        """
        Calculate Minimum Spanning Tree from building and street data.
        
        This is the main entry point that replaces the original calculate_mst function.
        It orchestrates all processing steps with clear intermediate results.
        
        Args:
            input_buildings: Building polygons layer
            streets_original: Original street network layer
            spatial_reference: Coordinate reference system to use
            
        Returns:
            QgsVectorLayer containing MST lines, or None if processing fails
        """
        try:
            # Step 1: Extract building centroids
            centroids_result = self.delaunay_processor.extract_building_centroids(input_buildings)
            
            if len(centroids_result.centroids) == 0:
                self.logger.log("No building centroids found", level="WARNING")
                return None
            
            # Step 2: Create Delaunay triangulation
            triangulation_edges = self.delaunay_processor.create_triangulation(centroids_result)
            
            # Create triangulation layer for street filtering
            triangulation_layer = self.delaunay_processor.create_triangulation_layer(
                triangulation_edges, spatial_reference
            )
            
            # Step 3: Process streets (remove short dead-ends)
            street_result = self.street_processor.process_streets(streets_original)
            
            # Step 4: Filter triangulation edges by streets
            filtered_edges = self.delaunay_processor.filter_edges_by_streets(
                triangulation_layer, street_result.filtered_streets
            )
            
            if len(filtered_edges) == 0:
                self.logger.log("No triangulation edges remaining after filtering", level="WARNING")
                return None
            
            # Step 5: Create Delaunay list for MST processing
            tri = Delaunay(centroids_result.points_array)
            delaunay_list, point_node_mapping = self.delaunay_processor.create_delaunay_list_with_nodes(
                filtered_edges, centroids_result.points_array, tri
            )
            
            if len(delaunay_list) == 0:
                self.logger.log("No valid edges for MST calculation", level="WARNING")
                return None
            
            # Step 6: Calculate MST
            mst_result = self.mst_calculator.calculate_mst_complete(
                delaunay_list,
                input_buildings,
                point_node_mapping,
                centroids_result.points_array,
                spatial_reference
            )
            
            if mst_result.mst_layer is None:
                self.logger.log("MST calculation failed", level="WARNING")
                return None

            return mst_result.mst_layer
            
        except Exception as e:
            self.logger.log(f"MST calculation failed with error: {str(e)}", level="CRITICAL")
            return None
    
    def get_detailed_result(
        self, 
        input_buildings: QgsVectorLayer,
        streets_original: QgsVectorLayer, 
        spatial_reference: QgsCoordinateReferenceSystem
    ) -> Optional[MSTResult]:
        """
        Get detailed MST calculation result with full information.
        
        Args:
            input_buildings: Building polygons layer
            streets_original: Original street network layer
            spatial_reference: Coordinate reference system to use
            
        Returns:
            MSTResult with detailed information, or None if processing fails
        """
        # This method provides the same calculation but returns full result object
        # instead of just the layer - useful for testing and detailed analysis
        
        try:
            # Follow the same workflow as calculate_mst but return full result
            centroids_result = self.delaunay_processor.extract_building_centroids(input_buildings)
            if len(centroids_result.centroids) == 0:
                return None
            
            triangulation_edges = self.delaunay_processor.create_triangulation(centroids_result)
            triangulation_layer = self.delaunay_processor.create_triangulation_layer(
                triangulation_edges, spatial_reference
            )
            
            street_result = self.street_processor.process_streets(streets_original)
            filtered_edges = self.delaunay_processor.filter_edges_by_streets(
                triangulation_layer, street_result.filtered_streets
            )
            
            if len(filtered_edges) == 0:
                return None
            
            tri = Delaunay(centroids_result.points_array)
            delaunay_list, point_node_mapping = self.delaunay_processor.create_delaunay_list_with_nodes(
                filtered_edges, centroids_result.points_array, tri
            )
            
            if len(delaunay_list) == 0:
                return None
            
            mst_result = self.mst_calculator.calculate_mst_complete(
                delaunay_list,
                input_buildings,
                point_node_mapping,
                centroids_result.points_array,
                spatial_reference
            )
            
            return mst_result
            
        except Exception as e:
            self.logger.log(f"Detailed MST calculation failed: {str(e)}", level="CRITICAL")
            return None


def calculate_mst(
    input_bdg: QgsVectorLayer, 
    streets_orig: QgsVectorLayer, 
    SpatialReference: QgsCoordinateReferenceSystem
) -> Optional[QgsVectorLayer]:
    """
    Compatibility function that maintains the original API for backward compatibility.
    Uses default configuration values from MSTConfig.
    
    Args:
        input_bdg: Building polygons layer  
        streets_orig: Original street network layer
        SpatialReference: Coordinate reference system
        
    Returns:
        QgsVectorLayer containing MST lines, or None if processing fails
    """
    # Create MST calculator with default configuration
    mst_creator = CreateMST()
    
    # Call the implementation
    return mst_creator.calculate_mst(input_bdg, streets_orig, SpatialReference)