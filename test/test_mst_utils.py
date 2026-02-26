# -*- coding: utf-8 -*-
"""Tests for helpers/mst_utils.py.

Covers MSTUtilities: unique_items, rounded_edge_key (pure Python) and
join_array_to_polygons, polygon_support_points_dict (QGIS layer operations).
"""
import pytest

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
)
from qgis.PyQt.QtCore import QMetaType

from ibtool.helpers.mst_utils import MSTUtilities


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_square_polygon_layer(x_offset: float = 0.0) -> QgsVectorLayer:
    """Return a one-feature polygon layer containing a 10×10 square."""
    layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "test_polys", "memory")
    feat = QgsFeature()
    feat.setGeometry(
        QgsGeometry.fromPolygonXY(
            [[
                QgsPointXY(x_offset + 0, 0),
                QgsPointXY(x_offset + 10, 0),
                QgsPointXY(x_offset + 10, 10),
                QgsPointXY(x_offset + 0, 10),
                QgsPointXY(x_offset + 0, 0),
            ]]
        )
    )
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return layer


# ── unique_items ──────────────────────────────────────────────────────────────

class TestUniqueItems:
    """Tests for MSTUtilities.unique_items."""

    @pytest.mark.unit
    def test_removes_duplicate_scalars(self):
        result = MSTUtilities.unique_items([1, 2, 2, 3, 3, 3])
        assert sorted(result) == [1, 2, 3]

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_list_returns_empty(self):
        assert MSTUtilities.unique_items([]) == []

    @pytest.mark.unit
    def test_all_unique_preserves_count(self):
        items = [10, 20, 30]
        result = MSTUtilities.unique_items(items)
        assert len(result) == 3

    @pytest.mark.unit
    def test_nested_lists_are_deduplicated_as_tuples(self):
        """Lists inside the input are converted to tuples before deduplication."""
        items = [[1, 2], [1, 2], [3, 4]]
        result = MSTUtilities.unique_items(items)
        assert len(result) == 2
        assert (1, 2) in result
        assert (3, 4) in result

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_single_item_list(self):
        assert MSTUtilities.unique_items([42]) == [42]


# ── rounded_edge_key ──────────────────────────────────────────────────────────

class TestRoundedEdgeKey:
    """Tests for MSTUtilities.rounded_edge_key."""

    @pytest.mark.unit
    def test_returns_two_element_tuple(self):
        key = MSTUtilities.rounded_edge_key(0.0, 0.0, 10.0, 10.0)
        assert isinstance(key, tuple)
        assert len(key) == 2

    @pytest.mark.unit
    def test_order_independent(self):
        """Swapping the two endpoints must produce the same key."""
        key1 = MSTUtilities.rounded_edge_key(0.0, 0.0, 10.0, 10.0)
        key2 = MSTUtilities.rounded_edge_key(10.0, 10.0, 0.0, 0.0)
        assert key1 == key2

    @pytest.mark.unit
    def test_result_is_lexicographically_sorted(self):
        """The two coordinate pairs in the key are in sorted order."""
        key = MSTUtilities.rounded_edge_key(5.0, 3.0, 1.0, 2.0)
        assert key == tuple(sorted(key))

    @pytest.mark.unit
    def test_default_precision_is_zero(self):
        """At default precision=0, coordinate values are rounded to integers."""
        key = MSTUtilities.rounded_edge_key(1.4, 2.6, 3.7, 4.1)
        for point in key:
            assert point[0] == round(point[0])
            assert point[1] == round(point[1])

    @pytest.mark.unit
    def test_higher_precision_retained(self):
        """With precision=2, values keep two decimal places."""
        key = MSTUtilities.rounded_edge_key(1.123, 4.567, 7.891, 2.345, precision=2)
        for point in key:
            assert point[0] == round(point[0], 2)
            assert point[1] == round(point[1], 2)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_identical_endpoints(self):
        """Two identical points produce a key with two equal coordinate pairs."""
        key = MSTUtilities.rounded_edge_key(5.0, 5.0, 5.0, 5.0)
        assert key[0] == key[1]


# ── join_array_to_polygons ────────────────────────────────────────────────────

class TestJoinArrayToPolygons:
    """Tests for MSTUtilities.join_array_to_polygons."""

    @pytest.mark.unit
    def test_adds_field_when_absent(self):
        layer = _make_square_polygon_layer()
        assert layer.fields().indexFromName("node") < 0
        MSTUtilities.join_array_to_polygons(layer, [], field_name="node")
        assert layer.fields().indexFromName("node") >= 0

    @pytest.mark.unit
    def test_sets_value_matching_centroid(self):
        """Centroid of a 10×10 square at origin is (5, 5); value must be written."""
        layer = _make_square_polygon_layer()
        data = [[5.0, 5.0, "A1"]]
        MSTUtilities.join_array_to_polygons(layer, data, field_name="node")
        feat = next(layer.getFeatures())
        assert feat["node"] == "A1"

    @pytest.mark.unit
    def test_field_not_duplicated_when_already_present(self):
        layer = _make_square_polygon_layer()
        layer.dataProvider().addAttributes([QgsField("node", QMetaType.QString)])
        layer.updateFields()
        count_before = layer.fields().count()
        MSTUtilities.join_array_to_polygons(layer, [], field_name="node")
        assert layer.fields().count() == count_before

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_data_array_no_crash(self):
        """Passing an empty data_array must not raise and must still add the field."""
        layer = _make_square_polygon_layer()
        MSTUtilities.join_array_to_polygons(layer, [], field_name="node")
        assert layer.fields().indexFromName("node") >= 0


# ── polygon_support_points_dict ───────────────────────────────────────────────

class TestPolygonSupportPointsDict:
    """Tests for MSTUtilities.polygon_support_points_dict."""

    def _make_keyed_layer(self, key_value: str = "A") -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "keyed_polys", "memory")
        layer.dataProvider().addAttributes([QgsField("key", QMetaType.QString)])
        layer.updateFields()
        feat = QgsFeature(layer.fields())
        feat["key"] = key_value
        feat.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0), QgsPointXY(10, 0),
                    QgsPointXY(10, 10), QgsPointXY(0, 10),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_returns_dict_with_field_value_as_key(self):
        layer = self._make_keyed_layer("A")
        result = MSTUtilities.polygon_support_points_dict(layer, "key")
        assert "A" in result

    @pytest.mark.unit
    def test_vertices_are_coordinate_tuples(self):
        layer = self._make_keyed_layer("B")
        result = MSTUtilities.polygon_support_points_dict(layer, "key")
        vertices = result["B"]
        assert len(vertices) > 0
        for v in vertices:
            assert len(v) == 2, "Each vertex must be an (x, y) tuple"

    @pytest.mark.unit
    def test_multiple_features_produce_multiple_keys(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "multi", "memory")
        layer.dataProvider().addAttributes([QgsField("key", QMetaType.QString)])
        layer.updateFields()
        features = []
        for i, k in enumerate(["X", "Y"]):
            f = QgsFeature(layer.fields())
            f["key"] = k
            x = float(i * 20)
            f.setGeometry(
                QgsGeometry.fromPolygonXY(
                    [[
                        QgsPointXY(x, 0), QgsPointXY(x + 10, 0),
                        QgsPointXY(x + 10, 10), QgsPointXY(x, 10),
                        QgsPointXY(x, 0),
                    ]]
                )
            )
            features.append(f)
        layer.dataProvider().addFeatures(features)
        result = MSTUtilities.polygon_support_points_dict(layer, "key")
        assert set(result.keys()) == {"X", "Y"}

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_returns_empty_dict(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "empty", "memory")
        layer.dataProvider().addAttributes([QgsField("key", QMetaType.QString)])
        layer.updateFields()
        result = MSTUtilities.polygon_support_points_dict(layer, "key")
        assert result == {}
