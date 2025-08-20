# -*- coding: utf-8 -*-
"""
Street Processor

Handles street data processing and filtering operations for MST calculations.
"""

from typing import List
from qgis.core import (
    QgsVectorLayer, QgsField, QgsDistanceArea, 
    QgsProcessing, edit
)
from qgis.PyQt.QtCore import QMetaType
from qgis import processing

from .mst_data_classes import StreetProcessingResult
from ...helpers.geometry_utils import nodes_detect
from ...helpers.logger import Logger
from ...helpers.qgis_defaults import QGISDefaults


class StreetProcessor:
    """Handles street network processing and filtering operations."""
    
    # Street processing parameters
    ROAD_LENGTH_THRESHOLD = 50.0
    """Maximum length for dead-end streets to be removed (meters)"""
    
    BUFFER_DISTANCE = 5.0
    """Buffer distance for intersection processing (meters)"""
    
    def __init__(self):
        """Initialize the street processor."""
        self.logger = Logger()
        self.qgis_defaults = QGISDefaults()
    
    def create_working_copy(self, original_streets: QgsVectorLayer) -> QgsVectorLayer:
        """
        Create a working copy of the streets layer.
        
        Args:
            original_streets: Original streets layer
            
        Returns:
            Working copy of streets layer
        """
        streets = QgsVectorLayer(
            f"LineString?crs={original_streets.crs().authid()}", 
            f"{self.config.temp_layer_prefix}_streets", 
            "memory"
        )
        
        data_provider = streets.dataProvider()
        data_provider.addFeatures(list(original_streets.getFeatures()))
        streets.updateExtents()
        
        return streets
    
    def process_intersections(self, streets_layer: QgsVectorLayer) -> QgsVectorLayer:
        """
        Find and process street intersections.
        
        Args:
            streets_layer: Streets layer to process
            
        Returns:
            Layer containing intersection points
        """
        # Find line intersections
        intersections = processing.run("native:lineintersections", {
            'INPUT': streets_layer,
            'INTERSECT': streets_layer,
            'INPUT_FIELDS': [],
            'INTERSECT_FIELDS': [],
            'INTERSECT_FIELDS_PREFIX': '',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        
        # Buffer intersection points
        intersection_buffer = processing.run("native:buffer", {
            'INPUT': intersections,
            'DISTANCE': self.BUFFER_DISTANCE,
            'SEGMENTS': self.qgis_defaults.buffer_segments,
            'END_CAP_STYLE': self.qgis_defaults.buffer_end_cap_style,
            'JOIN_STYLE': self.qgis_defaults.buffer_join_style,
            'MITER_LIMIT': self.qgis_defaults.buffer_miter_limit,
            'DISSOLVE': False,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        
        self.logger.log("Processed street intersections", level="INFO")
        
        return intersection_buffer
    
    def identify_dead_ends(
        self, 
        streets_layer: QgsVectorLayer, 
        intersection_buffer: QgsVectorLayer
    ) -> QgsVectorLayer:
        """
        Identify dead-end streets by finding nodes not at intersections.
        
        Args:
            streets_layer: Streets layer
            intersection_buffer: Buffered intersection points
            
        Returns:
            Layer containing dead-end streets
        """
        # Detect street nodes (endpoints)
        street_nodes = nodes_detect(streets_layer, 1)
        
        # Select nodes that intersect with intersection buffers
        processing.run("native:selectbylocation", {
            'INPUT': street_nodes,
            'PREDICATE': [0],  # intersects
            'INTERSECT': intersection_buffer,
            'METHOD': 0,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })
        
        # Remove nodes at intersections (keep only dead-end nodes)
        with edit(street_nodes):
            for feature in street_nodes.getFeatures():
                if feature.id() in street_nodes.selectedFeatureIds():
                    street_nodes.deleteFeature(feature.id())
        
        # Extract streets that intersect with remaining nodes (dead-ends)
        dead_end_streets = processing.run("native:extractbylocation", {
            'INPUT': streets_layer,
            'PREDICATE': [0],  # intersects
            'INTERSECT': street_nodes,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        
        self.logger.log("Identified dead-end streets", level="INFO")
        
        return dead_end_streets
    
    def calculate_street_lengths(self, streets_layer: QgsVectorLayer) -> None:
        """
        Add length field and calculate lengths for street features.
        
        Args:
            streets_layer: Streets layer to process
        """
        fields = streets_layer.fields()
        if not fields.indexFromName('length') >= 0:
            streets_layer.dataProvider().addAttributes([
                QgsField('length', QMetaType.Double)
            ])
            streets_layer.updateFields()
        
        distance_area = QgsDistanceArea()
        with edit(streets_layer):
            for feature in streets_layer.getFeatures():
                geom = feature.geometry()
                length = distance_area.measureLength(geom)
                feature['length'] = length
                streets_layer.updateFeature(feature)
        
        self.logger.log("Calculated street lengths", level="INFO")
    
    def filter_short_dead_ends(self, dead_end_streets: QgsVectorLayer) -> QgsVectorLayer:
        """
        Filter dead-end streets by length threshold.
        
        Args:
            dead_end_streets: Layer containing dead-end streets
            
        Returns:
            Layer containing short dead-end streets
        """
        short_dead_ends = processing.run("native:extractbyexpression", {
            'INPUT': dead_end_streets,
            'EXPRESSION': f'"length" < {self.ROAD_LENGTH_THRESHOLD}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']
        
        feature_count = short_dead_ends.featureCount()
        self.logger.log(
            f"Filtered {feature_count} short dead-end streets (< {self.ROAD_LENGTH_THRESHOLD}m)", 
            level="INFO"
        )
        
        return short_dead_ends
    
    def remove_short_dead_ends_from_streets(
        self, 
        streets_layer: QgsVectorLayer, 
        short_dead_ends: QgsVectorLayer
    ) -> int:
        """
        Remove short dead-end streets from the main streets layer.
        
        Args:
            streets_layer: Main streets layer
            short_dead_ends: Short dead-end streets to remove
            
        Returns:
            Number of streets removed
        """
        # Select streets that are equal to short dead-ends
        processing.run("native:selectbylocation", {
            'INPUT': streets_layer,
            'PREDICATE': [3],  # are equal
            'INTERSECT': short_dead_ends,
            'METHOD': 0,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })
        
        # Remove selected streets
        selected_ids = streets_layer.selectedFeatureIds()
        removed_count = len(selected_ids)
        
        with edit(streets_layer):
            for feature_id in selected_ids:
                streets_layer.deleteFeature(feature_id)
        
        self.logger.log(f"Removed {removed_count} short dead-end streets", level="INFO")
        
        return removed_count
    
    def process_streets(self, original_streets: QgsVectorLayer) -> StreetProcessingResult:
        """
        Complete street processing workflow.
        
        Args:
            original_streets: Original streets layer
            
        Returns:
            StreetProcessingResult with processed data
        """
        # Create working copy
        streets = self.create_working_copy(original_streets)
        
        # Process intersections
        intersection_buffer = self.process_intersections(streets)
        
        # Identify dead-end streets
        dead_end_streets = self.identify_dead_ends(streets, intersection_buffer)
        
        # Calculate lengths
        self.calculate_street_lengths(dead_end_streets)
        
        # Filter short dead-ends
        short_dead_ends = self.filter_short_dead_ends(dead_end_streets)
        
        # Remove short dead-ends from main streets
        removed_count = self.remove_short_dead_ends_from_streets(streets, short_dead_ends)
        
        return StreetProcessingResult(
            filtered_streets=streets,
            intersection_points=intersection_buffer,
            dead_end_streets=dead_end_streets,
            removed_street_count=removed_count
        )