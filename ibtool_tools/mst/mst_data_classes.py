# -*- coding: utf-8 -*-
"""
MST Data Classes

Data classes for type-safe interfaces between MST components.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem


@dataclass
class EdgeData:
    """Represents a single edge in the triangulation or MST."""

    start_point: Tuple[float, float]
    """Starting point coordinates (x, y)"""

    end_point: Tuple[float, float]
    """Ending point coordinates (x, y)"""

    weight: float
    """Edge weight (typically distance)"""

    node1_id: Optional[str] = None
    """ID of first node"""

    node2_id: Optional[str] = None
    """ID of second node"""


@dataclass
class TriangulationResult:
    """Result of Delaunay triangulation processing."""

    edges: List[EdgeData]
    """List of edges in the triangulation"""

    points_array: np.ndarray
    """Numpy array of point coordinates"""

    triangulation_layer: QgsVectorLayer
    """QGIS layer containing triangulation geometry"""

    point_node_mapping: List[List[float]]
    """Mapping of points to node IDs: [[x, y, node_id], ...]"""

    filtered_edge_count: int
    """Number of edges after filtering"""


@dataclass
class StreetProcessingResult:
    """Result of street processing operations."""

    filtered_streets: QgsVectorLayer
    """Streets layer after filtering"""

    intersection_points: QgsVectorLayer
    """Street intersection points"""

    dead_end_streets: QgsVectorLayer
    """Identified dead-end streets"""

    removed_street_count: int
    """Number of streets removed during processing"""


@dataclass
class MSTResult:
    """Final result of MST calculation."""

    mst_layer: QgsVectorLayer
    """Output layer containing MST edges"""

    edges: List[EdgeData]
    """List of MST edges with weights"""

    total_weight: float
    """Total weight of the MST"""

    node_count: int
    """Number of nodes in the MST"""

    edge_count: int
    """Number of edges in the MST"""

    crs: QgsCoordinateReferenceSystem
    """Coordinate reference system used"""


@dataclass
class BuildingCentroidsResult:
    """Result of building centroid extraction."""

    centroids: List[Tuple[float, float]]
    """List of centroid coordinates"""

    points_array: np.ndarray
    """Numpy array of centroid coordinates"""

    building_count: int
    """Number of buildings processed"""
