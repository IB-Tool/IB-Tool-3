# -*- coding: utf-8 -*-
"""
Tests for refactored MST class modules (STEP 8b).

Unit tests (no processing.run()) covering:
  Data classes   : EdgeData, BuildingCentroidsResult, MSTResult
  MSTCalculator  : calculate_minimum_spanning_tree() (pure networkx)
  StreetProcessor: class constants, create_working_copy()
  DelaunayProcessor: create_delaunay_list_with_nodes()
"""

import pytest
import numpy as np
import networkx as nx

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateReferenceSystem,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.mst import DelaunayProcessor, StreetProcessor, MSTCalculator
from ibtool.ibtool_tools.mst.mst_data_classes import (
    EdgeData, BuildingCentroidsResult, MSTResult,
)


# ---------------------------------------------------------------------------
# TestDataClasses
# ---------------------------------------------------------------------------

class TestDataClasses:
    """Unit tests for MST data classes (field types and default values)."""

    @pytest.mark.unit
    def test_edge_data_stores_start_end_and_weight(self):
        """EdgeData stores start point, end point, and weight with correct values."""
        edge = EdgeData(start_point=(1.0, 2.0), end_point=(3.0, 4.0), weight=5.0)

        assert edge.start_point == (1.0, 2.0)
        assert edge.end_point == (3.0, 4.0)
        assert edge.weight == 5.0

    @pytest.mark.unit
    def test_edge_data_node_ids_default_to_none(self):
        """EdgeData node IDs default to None when not explicitly provided."""
        edge = EdgeData(start_point=(0.0, 0.0), end_point=(1.0, 1.0), weight=1.0)

        assert edge.node1_id is None
        assert edge.node2_id is None

    @pytest.mark.unit
    def test_edge_data_optional_node_ids_can_be_set(self):
        """EdgeData accepts optional string node IDs."""
        edge = EdgeData(
            start_point=(0.0, 0.0), end_point=(1.0, 0.0),
            weight=1.0, node1_id="A", node2_id="B"
        )

        assert edge.node1_id == "A"
        assert edge.node2_id == "B"

    @pytest.mark.unit
    def test_building_centroids_result_stores_all_fields(self):
        """BuildingCentroidsResult stores centroids, points_array, and building_count."""
        pts = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = BuildingCentroidsResult(
            centroids=[(1.0, 2.0), (3.0, 4.0)],
            points_array=pts,
            building_count=2,
        )

        assert result.building_count == 2
        assert len(result.centroids) == 2
        assert result.points_array.shape == (2, 2)

    @pytest.mark.unit
    def test_mst_result_edge_count_matches_edges_list_length(self):
        """MSTResult.edge_count must equal len(edges) when constructed correctly."""
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        edges = [
            EdgeData((0.0, 0.0), (1.0, 0.0), 1.0),
            EdgeData((1.0, 0.0), (1.0, 1.0), 1.0),
        ]
        result = MSTResult(
            mst_layer=None, edges=edges, total_weight=2.0,
            node_count=3, edge_count=len(edges), crs=crs,
        )

        assert result.edge_count == len(result.edges)


# ---------------------------------------------------------------------------
# TestMSTCalculatorUnit
# ---------------------------------------------------------------------------

class TestMSTCalculatorUnit:
    """Unit tests for MSTCalculator using networkx graphs directly (no processing.run())."""

    @classmethod
    def setup_class(cls):
        cls.calculator = MSTCalculator()

    @pytest.mark.unit
    def test_calculate_mst_produces_n_minus_1_edges(self):
        """MST on a connected graph with n nodes yields exactly n−1 edges."""
        graph = nx.Graph()
        graph.add_edge("0", "1", weight=10.0)
        graph.add_edge("1", "2", weight=15.0)
        graph.add_edge("0", "2", weight=20.0)
        graph.add_edge("2", "3", weight=5.0)

        mst_edges = self.calculator.calculate_minimum_spanning_tree(graph)

        assert len(mst_edges) == graph.number_of_nodes() - 1

    @pytest.mark.unit
    def test_calculate_mst_empty_graph_returns_empty_list(self):
        """Empty graph produces an empty MST edge list without raising."""
        mst_edges = self.calculator.calculate_minimum_spanning_tree(nx.Graph())

        assert mst_edges == []

    @pytest.mark.unit
    def test_calculate_mst_all_edge_weights_are_positive(self):
        """Every returned MST edge carries a strictly positive weight."""
        graph = nx.Graph()
        graph.add_edge("0", "1", weight=3.0)
        graph.add_edge("1", "2", weight=7.0)
        graph.add_edge("0", "2", weight=12.0)

        mst_edges = self.calculator.calculate_minimum_spanning_tree(graph)

        for edge in mst_edges:
            assert edge.weight > 0, f"Non-positive MST edge weight: {edge.weight}"

    @pytest.mark.unit
    def test_calculate_mst_selects_minimum_total_weight(self):
        """MST total weight equals the sum of the cheapest spanning edges."""
        # Triangle: edges 1, 2, 100 → MST must use 1+2, omitting 100.
        graph = nx.Graph()
        graph.add_edge("A", "B", weight=1.0)
        graph.add_edge("B", "C", weight=2.0)
        graph.add_edge("A", "C", weight=100.0)

        mst_edges = self.calculator.calculate_minimum_spanning_tree(graph)
        total_weight = sum(e.weight for e in mst_edges)

        assert total_weight == pytest.approx(3.0)   # 1.0 + 2.0, not 1.0 + 100.0


# ---------------------------------------------------------------------------
# TestStreetProcessorUnit
# ---------------------------------------------------------------------------

class TestStreetProcessorUnit:
    """Unit tests for StreetProcessor constants and non-processing methods."""

    @classmethod
    def setup_class(cls):
        cls.processor = StreetProcessor()

    @pytest.mark.unit
    def test_road_length_threshold_is_50(self):
        """ROAD_LENGTH_THRESHOLD class constant equals 50.0 per project spec."""
        assert StreetProcessor.ROAD_LENGTH_THRESHOLD == 50.0

    @pytest.mark.unit
    def test_buffer_distance_is_5(self):
        """BUFFER_DISTANCE class constant equals 5.0 per project spec."""
        assert StreetProcessor.BUFFER_DISTANCE == 5.0

    @pytest.mark.unit
    def test_create_working_copy_has_same_feature_count(self):
        """create_working_copy produces a layer with the same number of features."""
        original = make_line_layer()
        feat = QgsFeature(original.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(10, 0)
        ]))
        original.dataProvider().addFeatures([feat])
        original.updateExtents()

        copy = self.processor.create_working_copy(original)

        assert copy.featureCount() == original.featureCount()

    @pytest.mark.unit
    def test_create_working_copy_is_independent_layer_object(self):
        """Working copy is a distinct layer object from the original."""
        original = make_line_layer()
        copy = self.processor.create_working_copy(original)

        assert copy is not original


# ---------------------------------------------------------------------------
# TestDelaunayProcessorModularUnit
# ---------------------------------------------------------------------------

class TestDelaunayProcessorModularUnit:
    """Unit tests for DelaunayProcessor.create_delaunay_list_with_nodes."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)
        cls.processor = DelaunayProcessor()

    def _four_building_layer(self) -> QgsVectorLayer:
        """Returns a layer with 4 buildings in a 2×2 grid."""
        layer = make_polygon_layer(self.CRS_ID)
        for i in range(4):
            x = float((i % 2) * 20)
            y = float((i // 2) * 20)
            add_feature_to_layer(layer, make_square_geom(x, y, 10))
        return layer

    @pytest.mark.unit
    def test_create_delaunay_list_returns_list_pair(self):
        """create_delaunay_list_with_nodes returns a (list, list) tuple."""
        from scipy.spatial import Delaunay as ScipyDelaunay

        layer = self._four_building_layer()
        centroids = self.processor.extract_building_centroids(layer)
        edges = self.processor.create_triangulation(centroids)
        tri = ScipyDelaunay(centroids.points_array)

        delaunay_list, point_node_mapping = self.processor.create_delaunay_list_with_nodes(
            edges, centroids.points_array, tri
        )

        assert isinstance(delaunay_list, list)
        assert isinstance(point_node_mapping, list)

    @pytest.mark.unit
    def test_create_delaunay_list_entries_have_5_elements(self):
        """Each entry in delaunay_list has exactly 5 elements: [edge_str, x1, y1, x2, y2]."""
        from scipy.spatial import Delaunay as ScipyDelaunay

        layer = self._four_building_layer()
        centroids = self.processor.extract_building_centroids(layer)
        edges = self.processor.create_triangulation(centroids)
        tri = ScipyDelaunay(centroids.points_array)

        delaunay_list, _ = self.processor.create_delaunay_list_with_nodes(
            edges, centroids.points_array, tri
        )

        for entry in delaunay_list:
            assert len(entry) == 5, \
                f"Expected 5 elements per entry, got {len(entry)}: {entry}"

    @pytest.mark.unit
    def test_point_node_mapping_entries_have_3_elements(self):
        """Each entry in point_node_mapping has exactly 3 elements: [x, y, node_id]."""
        from scipy.spatial import Delaunay as ScipyDelaunay

        layer = self._four_building_layer()
        centroids = self.processor.extract_building_centroids(layer)
        edges = self.processor.create_triangulation(centroids)
        tri = ScipyDelaunay(centroids.points_array)

        _, point_node_mapping = self.processor.create_delaunay_list_with_nodes(
            edges, centroids.points_array, tri
        )

        for entry in point_node_mapping:
            assert len(entry) == 3, \
                f"Expected 3 elements per mapping entry, got {len(entry)}: {entry}"
