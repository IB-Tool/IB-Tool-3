# -*- coding: utf-8 -*-
"""
QGIS Default Parameters

Global QGIS default parameters used across all tools.
These are technical QGIS settings, not business logic parameters.
"""

from dataclasses import dataclass


@dataclass
class QGISDefaults:
    """Standard QGIS parameters for consistent tool behavior across all plugins."""
    
    # Buffer operation defaults
    buffer_segments: int = 5
    """Number of segments for buffer operations"""
    
    buffer_end_cap_style: int = 0
    """End cap style for buffer operations (0=round, 1=flat, 2=square)"""
    
    buffer_join_style: int = 0
    """Join style for buffer operations (0=round, 1=miter, 2=bevel)"""
    
    buffer_miter_limit: float = 2.0
    """Miter limit for buffer operations"""
    
    # Processing defaults
    coordinate_precision: int = 0
    """Decimal places for coordinate rounding in edge keys"""
    
    # Layer naming conventions
    temp_layer_prefix: str = "temp"
    """Prefix for temporary layer names"""