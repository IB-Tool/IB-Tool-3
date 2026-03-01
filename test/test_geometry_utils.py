# -*- coding: utf-8 -*-
"""Tests for helpers/geometry_utils.py.

Focuses on functions that are testable without processing.run:
  - create_empty_layer
  - create_linestring_layer_from_array
  - shp_area2
  - get_hole_polygons

Functions that delegate entirely to processing.run (polyline2, shp_area,
shp_length, nodes_detect, intersect_polygons, select_and_save_by_location,
load_to_geopackage, split_layer_by_attribute, extract_polygons_from_lines)
are outside the scope of these unit tests.
"""
import pytest
from unittest.mock import Mock

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
)

from .utilities import get_qgis_app
from ibtool.helpers.geometry_utils import (
    create_empty_layer,
    create_linestring_layer_from_array,
    shp_area2,
    get_hole_polygons,
    create_polygons_from_lines,
    extract_polygons_from_lines,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_polygon_layer(squares=1, crs="EPSG:25833") -> QgsVectorLayer:
    """Return a polygon layer with ``squares`` 10×10 non-overlapping squares."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", "polys", "memory")
    feats = []
    for i in range(squares):
        x = float(i * 20)
        f = QgsFeature()
        f.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(x, 0), QgsPointXY(x + 10, 0),
                    QgsPointXY(x + 10, 10), QgsPointXY(x, 10),
                    QgsPointXY(x, 0),
                ]]
            )
        )
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


# ── create_empty_layer ────────────────────────────────────────────────────────

class TestCreateEmptyLayer:
    """Tests for create_empty_layer."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_valid_polygon_layer(self):
        layer = create_empty_layer("test", "Polygon", "EPSG:25833")
        assert layer.isValid()
        assert layer.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.unit
    def test_returns_valid_linestring_layer(self):
        layer = create_empty_layer("lines", "LineString", "EPSG:4326")
        assert layer.isValid()
        assert layer.geometryType() == QgsWkbTypes.LineGeometry

    @pytest.mark.unit
    def test_layer_has_id_and_name_fields(self):
        layer = create_empty_layer("test", "Polygon", "EPSG:25833")
        field_names = [f.name() for f in layer.fields()]
        assert "id" in field_names
        assert "name" in field_names

    @pytest.mark.unit
    def test_layer_is_initially_empty(self):
        layer = create_empty_layer("empty", "Polygon", "EPSG:25833")
        assert layer.featureCount() == 0

    @pytest.mark.unit
    def test_layer_name_is_set(self):
        layer = create_empty_layer("my_special_layer", "Polygon", "EPSG:25833")
        assert layer.name() == "my_special_layer"


# ── create_linestring_layer_from_array ────────────────────────────────────────

class TestCreateLinestringLayerFromArray:
    """Tests for create_linestring_layer_from_array."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_valid_layer(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        layer = create_linestring_layer_from_array([[[0, 0], [10, 0], 10.0]], crs, "lines")
        assert layer.isValid()

    @pytest.mark.unit
    def test_feature_count_matches_segments(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        data = [[[0, 0], [10, 0], 1.0], [[10, 0], [20, 0], 2.0]]
        layer = create_linestring_layer_from_array(data, crs, "lines")
        assert layer.featureCount() == 2

    @pytest.mark.unit
    def test_weight_attribute_is_set(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        data = [[[0, 0], [10, 0], 5.5]]
        layer = create_linestring_layer_from_array(data, crs, "lines")
        feat = next(layer.getFeatures())
        assert feat["weight"] == pytest.approx(5.5)

    @pytest.mark.unit
    def test_segment_without_weight_uses_none(self):
        """A segment with only two coordinates (no weight) must not crash."""
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        data = [[[0, 0], [10, 0]]]  # No weight element
        layer = create_linestring_layer_from_array(data, crs, "lines")
        assert layer.featureCount() == 1

    @pytest.mark.unit
    def test_geometry_type_is_linestring(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        layer = create_linestring_layer_from_array([[[0, 0], [10, 0]]], crs, "lines")
        assert layer.geometryType() == QgsWkbTypes.LineGeometry

    @pytest.mark.unit
    def test_output_geometry_is_valid(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        data = [[[0, 0], [10, 10], 14.14]]
        layer = create_linestring_layer_from_array(data, crs, "lines")
        feat = next(layer.getFeatures())
        geom = feat.geometry()
        assert not geom.isNull()
        assert not geom.isEmpty()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_data_array_returns_empty_layer(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        layer = create_linestring_layer_from_array([], crs, "empty")
        assert layer.isValid()
        assert layer.featureCount() == 0


# ── shp_area2 ─────────────────────────────────────────────────────────────────

class TestShpArea2:
    """Tests for shp_area2."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_true_for_valid_layer(self):
        layer = _make_polygon_layer(1)
        result = shp_area2(layer)
        assert result is True

    @pytest.mark.unit
    def test_adds_area_field(self):
        layer = _make_polygon_layer(1)
        assert "Area" not in [f.name() for f in layer.fields()]
        shp_area2(layer, field_name="Area")
        assert "Area" in [f.name() for f in layer.fields()]

    @pytest.mark.unit
    def test_area_values_are_positive(self):
        layer = _make_polygon_layer(2)
        shp_area2(layer, field_name="Area")
        areas = [feat["Area"] for feat in layer.getFeatures()]
        assert all(a > 0 for a in areas), "All computed areas must be positive"

    @pytest.mark.unit
    def test_area_value_matches_expected(self):
        """A 10×10 square must produce an area of 100 m²."""
        layer = _make_polygon_layer(1)
        shp_area2(layer, field_name="Area")
        feat = next(layer.getFeatures())
        assert feat["Area"] == pytest.approx(100.0, rel=1e-3)

    @pytest.mark.unit
    def test_custom_field_name(self):
        layer = _make_polygon_layer(1)
        shp_area2(layer, field_name="Flaeche")
        assert "Flaeche" in [f.name() for f in layer.fields()]

    @pytest.mark.unit
    def test_field_not_duplicated_when_already_present(self):
        layer = _make_polygon_layer(1)
        shp_area2(layer, field_name="Area")
        count_after_first = layer.fields().count()
        shp_area2(layer, field_name="Area")
        assert layer.fields().count() == count_after_first

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_false_for_invalid_layer(self):
        mock_layer = Mock()
        mock_layer.isValid.return_value = False
        result = shp_area2(mock_layer)
        assert result is False


# ── get_hole_polygons ─────────────────────────────────────────────────────────

class TestGetHolePolygons:
    """Tests for get_hole_polygons."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_layer_with_geometry(self, geom: QgsGeometry) -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "layer", "memory")
        feat = QgsFeature()
        feat.setGeometry(geom)
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    def _big_square(self) -> QgsGeometry:
        """100×100 square that contains the small square."""
        return QgsGeometry.fromPolygonXY(
            [[
                QgsPointXY(0, 0), QgsPointXY(100, 0),
                QgsPointXY(100, 100), QgsPointXY(0, 100),
                QgsPointXY(0, 0),
            ]]
        )

    def _small_square(self, x: float = 5.0) -> QgsGeometry:
        """10×10 square placed inside the big square."""
        return QgsGeometry.fromPolygonXY(
            [[
                QgsPointXY(x, x), QgsPointXY(x + 10, x),
                QgsPointXY(x + 10, x + 10), QgsPointXY(x, x + 10),
                QgsPointXY(x, x),
            ]]
        )

    def _far_square(self) -> QgsGeometry:
        """10×10 square far outside the big square."""
        return QgsGeometry.fromPolygonXY(
            [[
                QgsPointXY(500, 500), QgsPointXY(510, 500),
                QgsPointXY(510, 510), QgsPointXY(500, 510),
                QgsPointXY(500, 500),
            ]]
        )

    @pytest.mark.unit
    def test_returns_valid_layer(self):
        layer1 = self._make_layer_with_geometry(self._small_square())
        layer2 = self._make_layer_with_geometry(self._big_square())
        result = get_hole_polygons(layer1, layer2)
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.unit
    def test_feature_within_layer2_is_excluded(self):
        """A polygon from layer1 that lies within a layer2 polygon must be excluded."""
        small_inside = self._make_layer_with_geometry(self._small_square(x=5.0))
        big_container = self._make_layer_with_geometry(self._big_square())
        result = get_hole_polygons(small_inside, big_container)
        assert result.featureCount() == 0

    @pytest.mark.unit
    def test_feature_outside_layer2_is_included(self):
        """A polygon from layer1 not within any layer2 polygon must be returned."""
        far_poly = self._make_layer_with_geometry(self._far_square())
        big_container = self._make_layer_with_geometry(self._big_square())
        result = get_hole_polygons(far_poly, big_container)
        assert result.featureCount() == 1

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer2_returns_all_features(self):
        """With an empty layer2, all features from layer1 are holes."""
        layer1 = _make_polygon_layer(3)
        empty_layer2 = QgsVectorLayer("Polygon?crs=EPSG:25833", "empty", "memory")
        result = get_hole_polygons(layer1, empty_layer2)
        assert result.featureCount() == 3

    @pytest.mark.unit
    def test_result_geometries_are_valid(self):
        """All returned geometries must pass GEOS validity check."""
        far_poly = self._make_layer_with_geometry(self._far_square())
        big_container = self._make_layer_with_geometry(self._big_square())
        result = get_hole_polygons(far_poly, big_container)
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull()
            assert not geom.isEmpty()
            assert geom.isGeosValid()


# ── create_polygons_from_lines ────────────────────────────────────────────────

class TestCreatePolygonsFromLines:
    """Tests for create_polygons_from_lines.

    NOTE: Tests that pass actual line data to create_polygons_from_lines are
    intentionally omitted. The function's inner loop iterates over `current_ring`
    while simultaneously appending to it (geometry_utils.py:276-288). When any
    matching segment is found Python continues over the newly appended items,
    creating an infinite loop for every closed ring input.
    Only the early-exit paths (invalid input type, empty layer) are safe to test.
    """

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_raises_for_polygon_input(self):
        """Passing a polygon layer must raise ValueError."""
        poly_layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "poly", "memory")
        with pytest.raises(ValueError):
            create_polygons_from_lines(poly_layer)

    @pytest.mark.unit
    def test_raises_for_none_input(self):
        """Passing None as input must raise an exception."""
        with pytest.raises(Exception):
            create_polygons_from_lines(None)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_line_layer_returns_empty_polygon_layer(self):
        """An empty line layer must return a valid but feature-less polygon layer."""
        empty_layer = QgsVectorLayer("LineString?crs=EPSG:25833", "empty", "memory")
        result = create_polygons_from_lines(empty_layer)
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0


# ── extract_polygons_from_lines ───────────────────────────────────────────────

class TestExtractPolygonsFromLines:
    """Tests for extract_polygons_from_lines.

    NOTE: Tests that pass actual line data to extract_polygons_from_lines are
    intentionally omitted. The function calls nx.simple_cycles(graph.to_directed()),
    which internally triggers a pandas → pyarrow import chain. On Windows with
    QGIS 3.40 the pyarrow DLL version is incompatible with the test environment,
    causing a fatal Windows exception (0xc0000139 STATUS_ENTRYPOINT_NOT_FOUND)
    that crashes the entire test process and corrupts subsequent QGIS module state.
    Only the early-exit path (wrong geometry type) is safe to test.
    """

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_raises_for_polygon_layer_input(self):
        """Passing a polygon layer must raise ValueError."""
        poly_layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "poly", "memory")
        with pytest.raises(ValueError):
            extract_polygons_from_lines(poly_layer)


# ── shp_area2 — additional edge-case branches ─────────────────────────────────

class TestShpArea2ExtraBranches:
    """Additional edge-case tests for shp_area2 not covered by TestShpArea2."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_layer_with_null_geometry(self) -> QgsVectorLayer:
        """Polygon layer with one feature that has a null geometry."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "null_geom", "memory")
        f = QgsFeature()
        # do NOT set geometry → null geometry
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_layer_with_null_geometry_returns_true_and_does_not_crash(self):
        """A feature with null geometry must be skipped gracefully; returns True."""
        layer = self._make_layer_with_null_geometry()
        result = shp_area2(layer, field_name="Area")
        assert result is True

    @pytest.mark.unit
    def test_field_already_present_logs_warning_via_logger(self):
        """When field already exists, shp_area2 logs a WARNING and returns True."""
        from unittest.mock import MagicMock
        mock_logger = MagicMock()
        layer = _make_polygon_layer(1)
        shp_area2(layer, field_name="Area")     # add field first
        result = shp_area2(layer, field_name="Area", logger=mock_logger)
        assert result is True
        mock_logger.log.assert_called()
        # The WARNING call should reference the field name
        warning_args = [call for call in mock_logger.log.call_args_list
                        if "WARNING" in str(call)]
        assert warning_args, "Expected at least one WARNING log for existing field"

    @pytest.mark.unit
    def test_exception_during_edit_returns_false(self):
        """If editing raises an exception, shp_area2 must return False."""
        from unittest.mock import MagicMock, patch
        mock_logger = MagicMock()
        layer = _make_polygon_layer(1)
        with patch("ibtool.helpers.geometry_utils.edit", side_effect=Exception("edit failed")):
            result = shp_area2(layer, field_name="Area", logger=mock_logger)
        assert result is False
