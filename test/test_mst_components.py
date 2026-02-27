# -*- coding: utf-8 -*-
"""
Tests for MST helper components (STEP 8a).

Unit tests (no processing.run()) covering:
  MSTUtilities : unique_items(), rounded_edge_key(),
                 polygon_support_points_dict(), join_array_to_polygons()
  DelaunayProcessor : extract_building_centroids(), create_triangulation(),
                      create_triangulation_layer()
"""

import pytest

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateReferenceSystem, QgsField,
)
from qgis.PyQt.QtCore import QVariant

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.helpers.mst_utils import MSTUtilities
from ibtool.ibtool_tools.mst import DelaunayProcessor
from ibtool.ibtool_tools.mst.mst_data_classes import EdgeData


# ---------------------------------------------------------------------------
# TestMSTUtilitiesUnit
# ---------------------------------------------------------------------------

class TestMSTUtilitiesUnit:
    """Unit tests for MSTUtilities helper functions."""

    # --- unique_items ---

    @pytest.mark.unit
    def test_unique_items_removes_duplicates(self):
        """Removes duplicate entries and returns only distinct items."""
        result = MSTUtilities.unique_items([[1, 2], [1, 2], [3, 4]])
        assert len(result) == 2

    @pytest.mark.unit
    def test_unique_items_empty_list_returns_empty(self):
        """Returns empty list when given an empty list."""
        assert MSTUtilities.unique_items([]) == []

    @pytest.mark.unit
    def test_unique_items_single_element_returns_one_item(self):
        """Returns a one-element list when given a single-element list."""
        result = MSTUtilities.unique_items([[5, 6]])
        assert len(result) == 1

    # --- rounded_edge_key ---

    @pytest.mark.unit
    def test_rounded_edge_key_is_order_independent(self):
        """Produces identical key regardless of which point is listed first."""
        key_ab = MSTUtilities.rounded_edge_key(1.0, 2.0, 3.0, 4.0)
        key_ba = MSTUtilities.rounded_edge_key(3.0, 4.0, 1.0, 2.0)
        assert key_ab == key_ba

    @pytest.mark.unit
    def test_rounded_edge_key_applies_precision_rounding(self):
        """Rounds coordinates to the requested precision so close values collapse."""
        key1 = MSTUtilities.rounded_edge_key(1.1, 2.1, 3.1, 4.1, precision=0)
        key2 = MSTUtilities.rounded_edge_key(1.4, 2.4, 3.4, 4.4, precision=0)
        assert key1 == key2   # both round to (1,2)↔(3,4)

    # --- polygon_support_points_dict ---

    @pytest.mark.unit
    def test_polygon_support_points_dict_empty_layer_returns_empty_dict(self):
        """Returns empty dict for a layer with no features."""
        layer = make_polygon_layer()
        layer.dataProvider().addAttributes([QgsField("node", QVariant.String)])
        layer.updateFields()

        result = MSTUtilities.polygon_support_points_dict(layer, "node")

        assert result == {}

    @pytest.mark.unit
    def test_polygon_support_points_dict_maps_field_to_vertex_list(self):
        """Maps each field value to a non-empty list of (x, y) vertex tuples."""
        layer = make_polygon_layer()
        layer.dataProvider().addAttributes([QgsField("node", QVariant.String)])
        layer.updateFields()
        feat = QgsFeature(layer.fields())
        feat.setGeometry(make_square_geom(0, 0, 10))
        feat.setAttribute("node", "42")
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()

        result = MSTUtilities.polygon_support_points_dict(layer, "node")

        assert "42" in result
        vertices = result["42"]
        assert isinstance(vertices, list)
        assert len(vertices) > 0
        for pt in vertices:
            assert len(pt) == 2    # each entry is (x, y)

    # --- join_array_to_polygons ---

    @pytest.mark.unit
    def test_join_array_to_polygons_adds_field_when_absent(self):
        """Adds the target field to the layer if it does not already exist."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 10))
        centroid = list(layer.getFeatures())[0].geometry().centroid().asPoint()

        MSTUtilities.join_array_to_polygons(
            layer, [[centroid.x(), centroid.y(), 7]], field_name="node"
        )

        assert layer.fields().indexFromName("node") >= 0

    @pytest.mark.unit
    def test_join_array_to_polygons_assigns_correct_node_value(self):
        """Assigns the correct node ID to a feature whose centroid matches the array."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 10))
        centroid = list(layer.getFeatures())[0].geometry().centroid().asPoint()

        MSTUtilities.join_array_to_polygons(
            layer, [[centroid.x(), centroid.y(), 99]], field_name="node"
        )

        feat = list(layer.getFeatures())[0]
        assert str(feat["node"]) == "99"


# ---------------------------------------------------------------------------
# TestDelaunayProcessorUnit
# ---------------------------------------------------------------------------

class TestDelaunayProcessorUnit:
    """Unit tests for DelaunayProcessor methods that do not call processing.run()."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)
        cls.processor = DelaunayProcessor()

    # --- extract_building_centroids ---

    @pytest.mark.unit
    def test_extract_centroids_count_matches_building_count(self):
        """Returns exactly one centroid per building polygon."""
        layer = make_polygon_layer(self.CRS_ID)
        for i in range(4):
            add_feature_to_layer(layer, make_square_geom(float(i * 20), 0.0, 10))

        result = self.processor.extract_building_centroids(layer)

        assert len(result.centroids) == 4
        assert result.building_count == 4
        assert result.points_array.shape == (4, 2)

    @pytest.mark.unit
    def test_extract_centroids_empty_layer_returns_empty_result(self):
        """Returns empty centroid list and zero building count for an empty layer."""
        layer = make_polygon_layer(self.CRS_ID)

        result = self.processor.extract_building_centroids(layer)

        assert result.centroids == []
        assert result.building_count == 0

    # --- create_triangulation ---

    @pytest.mark.unit
    def test_create_triangulation_returns_at_least_n_minus_1_edges(self):
        """Delaunay triangulation of n points has at least n−1 edges."""
        layer = make_polygon_layer(self.CRS_ID)
        # 2×2 grid — centroids at (5,5), (35,5), (5,35), (35,35): non-collinear
        for x, y in [(0.0, 0.0), (30.0, 0.0), (0.0, 30.0), (30.0, 30.0)]:
            add_feature_to_layer(layer, make_square_geom(x, y, 10))
        centroids = self.processor.extract_building_centroids(layer)

        edges = self.processor.create_triangulation(centroids)

        assert len(edges) >= 3   # n−1 = 3 for 4 points

    @pytest.mark.unit
    def test_create_triangulation_all_edge_weights_are_positive(self):
        """Every triangulation edge carries a strictly positive weight."""
        layer = make_polygon_layer(self.CRS_ID)
        # 2×2 grid — non-collinear so Delaunay produces actual edges
        for x, y in [(0.0, 0.0), (30.0, 0.0), (0.0, 30.0), (30.0, 30.0)]:
            add_feature_to_layer(layer, make_square_geom(x, y, 10))
        centroids = self.processor.extract_building_centroids(layer)

        edges = self.processor.create_triangulation(centroids)

        for edge in edges:
            assert edge.weight > 0, f"Non-positive weight: {edge.weight}"

    # --- create_triangulation_layer ---

    @pytest.mark.unit
    def test_create_triangulation_layer_returns_valid_layer_with_correct_count(self):
        """Returns a valid QgsVectorLayer whose feature count matches the edge list."""
        edges = [
            EdgeData(start_point=(0.0, 0.0), end_point=(10.0, 0.0), weight=10.0),
            EdgeData(start_point=(0.0, 0.0), end_point=(0.0, 10.0), weight=10.0),
        ]

        layer = self.processor.create_triangulation_layer(edges, self.crs)

        assert layer is not None
        assert isinstance(layer, QgsVectorLayer)
        assert layer.isValid()
        assert layer.featureCount() == 2

    @pytest.mark.unit
    def test_create_triangulation_layer_empty_edges_returns_empty_layer(self):
        """Returns a valid but empty layer for an empty edge list."""
        layer = self.processor.create_triangulation_layer([], self.crs)

        assert layer is not None
        assert isinstance(layer, QgsVectorLayer)
        assert layer.isValid()
        assert layer.featureCount() == 0
