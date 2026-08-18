"""
Tests for helpers/check.py — InputValidator and ValidationResult.

Coverage:
- ValidationResult dataclass (pure Python)
- InputValidator._check_crs
- InputValidator._check_feature_counts
- InputValidator._check_geometries
- InputValidator._check_hu_layer
- InputValidator._check_rn_layer
- InputValidator._check_aux_layer
- InputValidator._check_part_layer
- InputValidator._check_multipart_lines
- InputValidator._check_part_hu_ratio
- InputValidator._check_filter_file
- InputValidator._check_output_paths
- InputValidator._check_params
- InputValidator._check_validity_processing  (integration, mocked variant)
"""

import os
import pytest
import tempfile
from unittest.mock import MagicMock, patch

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsWkbTypes,
)
from PyQt5.QtCore import QVariant

from .utilities import get_qgis_app
from helpers.check import ValidationResult, InputValidator


# ---------------------------------------------------------------------------
# Layer factory helpers
# ---------------------------------------------------------------------------

def _make_polygon_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Create an empty in-memory polygon layer."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", "test_polygon", "memory")
    layer.updateFields()
    return layer


def _make_line_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Create an empty in-memory line layer."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", "test_line", "memory")
    layer.updateFields()
    return layer


def _make_square_geom(x: float = 0.0, y: float = 0.0, size: float = 1.0) -> QgsGeometry:
    """Create a simple valid square polygon geometry."""
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x, y),
        QgsPointXY(x + size, y),
        QgsPointXY(x + size, y + size),
        QgsPointXY(x, y + size),
        QgsPointXY(x, y),
    ]])


def _add_polygon_feature(layer: QgsVectorLayer, **field_values) -> QgsFeature:
    """Add one valid square polygon feature to a layer."""
    feat = QgsFeature(layer.fields())
    feat.setGeometry(_make_square_geom())
    for name, value in field_values.items():
        feat[name] = value
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat


# ---------------------------------------------------------------------------
# TestValidationResult — pure unit, no QGIS required
# ---------------------------------------------------------------------------

class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    @pytest.mark.unit
    def test_initial_state_is_valid(self):
        """Freshly created ValidationResult has no errors and is_valid=True."""
        result = ValidationResult()
        assert result.is_valid
        assert result.errors == []
        assert result.warnings == []

    @pytest.mark.unit
    def test_add_error_makes_invalid(self):
        """Adding an error sets is_valid to False."""
        result = ValidationResult()
        result.add_error("some error")
        assert not result.is_valid

    @pytest.mark.unit
    def test_warnings_alone_do_not_invalidate(self):
        """Warnings do not make the result invalid."""
        result = ValidationResult()
        result.add_warning("just a warning")
        assert result.is_valid

    @pytest.mark.unit
    def test_multiple_errors_are_accumulated(self):
        """Multiple add_error calls are all stored."""
        result = ValidationResult()
        result.add_error("error 1")
        result.add_error("error 2")
        assert len(result.errors) == 2

    @pytest.mark.unit
    def test_multiple_warnings_are_accumulated(self):
        """Multiple add_warning calls are all stored."""
        result = ValidationResult()
        result.add_warning("w1")
        result.add_warning("w2")
        assert len(result.warnings) == 2


# ---------------------------------------------------------------------------
# TestCheckCrs — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckCrs:
    """Tests for InputValidator._check_crs."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_matching_crs_no_error(self):
        """No error when layer CRS matches expected CRS."""
        layer = _make_polygon_layer("EPSG:25833")
        expected = QgsCoordinateReferenceSystem("EPSG:25833")
        result = ValidationResult()
        self.validator._check_crs(layer, "TestLayer", expected, result)
        assert result.is_valid

    @pytest.mark.unit
    def test_mismatched_crs_adds_error(self):
        """Error when layer CRS differs from expected CRS."""
        layer = _make_polygon_layer("EPSG:4326")
        expected = QgsCoordinateReferenceSystem("EPSG:25833")
        result = ValidationResult()
        self.validator._check_crs(layer, "TestLayer", expected, result)
        assert not result.is_valid
        assert any("CRS" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckFeatureCounts — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckFeatureCounts:
    """Tests for InputValidator._check_feature_counts."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_adds_error(self):
        """Error when the HU layer has zero features."""
        hu_layer = _make_polygon_layer()
        result = ValidationResult()
        self.validator._check_feature_counts(
            {"Building footprints (HU)": hu_layer}, result
        )
        assert not result.is_valid
        assert any("empty" in e.lower() for e in result.errors)

    @pytest.mark.unit
    def test_too_few_features_adds_error(self):
        """Error when feature count is below the minimum threshold."""
        hu_layer = _make_polygon_layer()
        feats = [QgsFeature(hu_layer.fields()) for _ in range(10)]
        for i, f in enumerate(feats):
            f.setGeometry(_make_square_geom(x=float(i)))
        hu_layer.dataProvider().addFeatures(feats)

        result = ValidationResult()
        self.validator._check_feature_counts(
            {"Building footprints (HU)": hu_layer}, result
        )
        assert not result.is_valid

    @pytest.mark.unit
    def test_sufficient_features_no_error(self):
        """No error when feature count meets the minimum threshold."""
        hu_layer = _make_polygon_layer()
        feats = [QgsFeature(hu_layer.fields()) for _ in range(60)]
        for i, f in enumerate(feats):
            f.setGeometry(_make_square_geom(x=float(i)))
        hu_layer.dataProvider().addFeatures(feats)

        result = ValidationResult()
        self.validator._check_feature_counts(
            {"Building footprints (HU)": hu_layer}, result
        )
        assert result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_part_layer_adds_error(self):
        """Error when the Part layer has zero features."""
        part_layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "part", "memory")
        part_layer.dataProvider().addAttributes([QgsField("NAME", QVariant.String)])
        part_layer.updateFields()
        result = ValidationResult()
        self.validator._check_feature_counts(
            {"Partitioning (Part)": part_layer}, result
        )
        assert not result.is_valid
        assert any("empty" in e.lower() for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_unknown_layer_name_is_skipped(self):
        """Layers not in the min_counts dict produce no error."""
        unknown_layer = _make_polygon_layer()
        result = ValidationResult()
        self.validator._check_feature_counts(
            {"Unknown Layer": unknown_layer}, result
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# TestCheckGeometries — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckGeometries:
    """Tests for InputValidator._check_geometries."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_valid_geometry_no_errors(self):
        """No errors when all features have valid geometries."""
        layer = _make_polygon_layer()
        _add_polygon_feature(layer)
        result = ValidationResult()
        self.validator._check_geometries(layer, "TestLayer", result)
        assert result.is_valid
        assert result.warnings == []

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_geometry_adds_error(self):
        """Error when a feature has null geometry."""
        layer = _make_polygon_layer()
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry())  # null
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_geometries(layer, "TestLayer", result)
        assert not result.is_valid
        assert any("NULL" in e for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_geometry_adds_error(self):
        """Error when a feature has empty geometry."""
        layer = _make_polygon_layer()
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromWkt("POLYGON EMPTY"))
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_geometries(layer, "TestLayer", result)
        assert not result.is_valid
        assert any("empty" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckHuLayer — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckHuLayer:
    """Tests for InputValidator._check_hu_layer."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    def _make_hu_layer(self, field_name: str = "fkt") -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "hu", "memory")
        layer.dataProvider().addAttributes([QgsField(field_name, QVariant.String)])
        layer.updateFields()
        return layer

    @pytest.mark.unit
    def test_missing_fkt_and_funktion_field_adds_error(self):
        """Error when neither 'fkt' nor 'funktion' field exists."""
        layer = _make_polygon_layer()
        _add_polygon_feature(layer)
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert not result.is_valid
        assert any("fkt" in e.lower() or "funktion" in e.lower() for e in result.errors)

    @pytest.mark.unit
    def test_valid_atkis_fkt_no_error(self):
        """No error for a polygon layer with valid ATKIS fkt values."""
        layer = self._make_hu_layer("fkt")
        _add_polygon_feature(layer, fkt="31001_1000")
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    @pytest.mark.unit
    def test_funktion_field_accepted_as_alternative(self):
        """'funktion' is accepted as alternative to 'fkt'."""
        layer = self._make_hu_layer("funktion")
        _add_polygon_feature(layer, funktion="31001_1000")
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_fkt_value_adds_warning(self):
        """Warning (not error) when fkt value is NULL — processing can still continue."""
        layer = self._make_hu_layer("fkt")
        _add_polygon_feature(layer, fkt=None)
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert result.is_valid  # NULL fkt is a warning, not a blocking error
        assert len(result.warnings) > 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_fkt_value_zero_silently_accepted(self):
        """Value '0' in fkt is accepted without error or warning."""
        layer = self._make_hu_layer("fkt")
        _add_polygon_feature(layer, fkt="0")
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert result.is_valid
        assert result.warnings == []

    @pytest.mark.unit
    def test_invalid_fkt_format_adds_warning(self):
        """Warning when fkt values do not match ATKIS pattern NNNNN_NNNN."""
        layer = self._make_hu_layer("fkt")
        _add_polygon_feature(layer, fkt="INVALID_FORMAT")
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert len(result.warnings) > 0

    @pytest.mark.unit
    def test_wrong_geometry_type_adds_error(self):
        """Error when HU layer is not polygon geometry."""
        layer = _make_line_layer()
        result = ValidationResult()
        self.validator._check_hu_layer(layer, result)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# TestCheckRnLayer — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckRnLayer:
    """Tests for InputValidator._check_rn_layer."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_line_geometry_no_error(self):
        """No error for a line-geometry layer."""
        layer = _make_line_layer()
        result = ValidationResult()
        self.validator._check_rn_layer(layer, result)
        assert result.is_valid

    @pytest.mark.unit
    def test_polygon_geometry_adds_error(self):
        """Error when RN layer has polygon instead of line geometry."""
        layer = _make_polygon_layer()
        result = ValidationResult()
        self.validator._check_rn_layer(layer, result)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# TestCheckAuxLayer — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckAuxLayer:
    """Tests for InputValidator._check_aux_layer."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_line_geometry_no_error(self):
        """No error for a line-geometry Aux layer."""
        layer = _make_line_layer()
        result = ValidationResult()
        self.validator._check_aux_layer(layer, result)
        assert result.is_valid

    @pytest.mark.unit
    def test_polygon_geometry_adds_error(self):
        """Error when Aux layer has polygon instead of line geometry."""
        layer = _make_polygon_layer()
        result = ValidationResult()
        self.validator._check_aux_layer(layer, result)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# TestCheckPartLayer — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckPartLayer:
    """Tests for InputValidator._check_part_layer."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    def _make_part_layer(self, name_value=None) -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "part", "memory")
        layer.dataProvider().addAttributes([QgsField("NAME", QVariant.String)])
        layer.updateFields()
        feat = QgsFeature(layer.fields())
        feat.setGeometry(_make_square_geom(size=10.0))
        feat["NAME"] = name_value
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_missing_name_field_adds_error(self):
        """Error when the NAME field is absent from the layer."""
        layer = _make_polygon_layer()
        _add_polygon_feature(layer)
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert not result.is_valid
        assert any("NAME" in e for e in result.errors)

    @pytest.mark.unit
    def test_valid_part_name_no_error(self):
        """No error when NAME follows the PART_<number> pattern."""
        layer = self._make_part_layer("PART_36")
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    @pytest.mark.unit
    def test_large_part_number_accepted(self):
        """PART_433 and similar large numbers are valid."""
        layer = self._make_part_layer("PART_433")
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert result.is_valid, f"Unexpected errors: {result.errors}"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_name_value_adds_error(self):
        """Error when NAME value is NULL."""
        layer = self._make_part_layer(None)
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_invalid_name_format_adds_error(self):
        """Error when NAME does not match PART_<number> (e.g. 'zone_1')."""
        layer = self._make_part_layer("zone_1")
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_line_geometry_adds_error(self):
        """Error when Part layer is not polygon geometry."""
        layer = QgsVectorLayer("LineString?crs=EPSG:25833", "part", "memory")
        layer.dataProvider().addAttributes([QgsField("NAME", QVariant.String)])
        layer.updateFields()
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(1, 1)
        ]))
        feat["NAME"] = "PART_1"
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_part_layer(layer, result)
        assert not result.is_valid
        assert any("Polygon geometry required" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestCheckMultipartLines — requires QGIS
# ---------------------------------------------------------------------------

class TestCheckMultipartLines:
    """Tests for InputValidator._check_multipart_lines."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_singlepart_line_no_error(self):
        """No error for a layer with single-part LineString features."""
        layer = _make_line_layer()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(1, 1)
        ]))
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_multipart_lines(layer, "RN", result)
        assert result.is_valid

    @pytest.mark.unit
    def test_multilinestring_single_component_no_error(self):
        """No error for a MultiLineString with exactly one component."""
        layer = QgsVectorLayer("MultiLineString?crs=EPSG:25833", "rn", "memory")
        layer.updateFields()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromMultiPolylineXY([
            [QgsPointXY(0, 0), QgsPointXY(1, 1)]
        ]))
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_multipart_lines(layer, "RN", result)
        assert result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_multilinestring_multiple_components_adds_error(self):
        """Error when a MultiLineString has more than one line component."""
        layer = QgsVectorLayer("MultiLineString?crs=EPSG:25833", "rn", "memory")
        layer.updateFields()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromMultiPolylineXY([
            [QgsPointXY(0, 0), QgsPointXY(1, 1)],
            [QgsPointXY(2, 2), QgsPointXY(3, 3)],
        ]))
        layer.dataProvider().addFeatures([feat])
        result = ValidationResult()
        self.validator._check_multipart_lines(layer, "RN", result)
        assert not result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_polygon_layer_is_skipped(self):
        """Non-line layers are silently skipped without any error."""
        layer = _make_polygon_layer()
        _add_polygon_feature(layer)
        result = ValidationResult()
        self.validator._check_multipart_lines(layer, "HU", result)
        assert result.is_valid


# ---------------------------------------------------------------------------
# TestCheckPartHuRatio — uses mocks, no QGIS required
# ---------------------------------------------------------------------------

class TestCheckPartHuRatio:
    """Tests for InputValidator._check_part_hu_ratio."""

    @pytest.mark.unit
    def test_ratio_within_threshold_no_warning(self):
        """No warning when HU/Part ratio is within MAX_PART_TO_HU_RATIO."""
        validator = InputValidator()
        part_layer = MagicMock()
        part_layer.featureCount.return_value = 100
        hu_layer = MagicMock()
        hu_layer.featureCount.return_value = 5000  # ratio = 50
        result = ValidationResult()
        validator._check_part_hu_ratio(part_layer, hu_layer, result)
        assert result.is_valid
        assert result.warnings == []

    @pytest.mark.unit
    def test_ratio_exceeds_threshold_adds_warning(self):
        """Warning when HU/Part ratio exceeds MAX_PART_TO_HU_RATIO (10000)."""
        validator = InputValidator()
        part_layer = MagicMock()
        part_layer.featureCount.return_value = 1
        hu_layer = MagicMock()
        hu_layer.featureCount.return_value = 15000
        result = ValidationResult()
        validator._check_part_hu_ratio(part_layer, hu_layer, result)
        assert len(result.warnings) > 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_zero_part_features_skipped(self):
        """No crash and no warning when part layer has 0 features."""
        validator = InputValidator()
        part_layer = MagicMock()
        part_layer.featureCount.return_value = 0
        hu_layer = MagicMock()
        hu_layer.featureCount.return_value = 1000
        result = ValidationResult()
        validator._check_part_hu_ratio(part_layer, hu_layer, result)
        assert result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_zero_hu_features_skipped(self):
        """No crash and no warning when hu layer has 0 features."""
        validator = InputValidator()
        part_layer = MagicMock()
        part_layer.featureCount.return_value = 10
        hu_layer = MagicMock()
        hu_layer.featureCount.return_value = 0
        result = ValidationResult()
        validator._check_part_hu_ratio(part_layer, hu_layer, result)
        assert result.is_valid


# ---------------------------------------------------------------------------
# TestCheckFilterFile — pure Python, no QGIS required
# ---------------------------------------------------------------------------

class TestCheckFilterFile:
    """Tests for InputValidator._check_filter_file."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_path_adds_error(self):
        """Error when filter file path is empty."""
        validator = InputValidator()
        result = ValidationResult()
        validator._check_filter_file("", result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_nonexistent_file_adds_error(self):
        """Error when filter file path points to a non-existent file."""
        validator = InputValidator()
        result = ValidationResult()
        validator._check_filter_file("/nonexistent/path/filter.txt", result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_valid_filter_file_no_errors(self):
        """No errors and no warnings for a correctly formatted filter file."""
        validator = InputValidator()
        content = (
            "#Filter positive\n"
            "31001_1000, Wohngebaeude\n"
            "31001_1010, Wohnhaus\n"
            "\n"
            "#Filter negative\n"
            "31001_1310, Freizeit\n"
            "31001_2600, Entsorgung\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert result.is_valid, f"Errors: {result.errors}"
            assert result.warnings == [], f"Warnings: {result.warnings}"
        finally:
            os.unlink(path)

    @pytest.mark.unit
    def test_missing_positive_section_adds_error(self):
        """Error when '#Filter positive' section header is missing."""
        validator = InputValidator()
        content = "#Filter negative\n31001_1310, Freizeit\n"
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert not result.is_valid
        finally:
            os.unlink(path)

    @pytest.mark.unit
    def test_missing_negative_section_adds_error(self):
        """Error when '#Filter negative' section header is missing."""
        validator = InputValidator()
        content = "#Filter positive\n31001_1000, Wohnhaus\n"
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert not result.is_valid
        finally:
            os.unlink(path)

    @pytest.mark.unit
    def test_wrong_section_order_adds_error(self):
        """Error when negative section appears before positive section."""
        validator = InputValidator()
        content = (
            "#Filter negative\n31001_1310, Freizeit\n"
            "#Filter positive\n31001_1000, Wohnhaus\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert not result.is_valid
            assert any("before" in e.lower() for e in result.errors)
        finally:
            os.unlink(path)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_positive_section_adds_error(self):
        """Error when positive section exists but has no entries."""
        validator = InputValidator()
        content = (
            "#Filter positive\n"
            "\n"
            "#Filter negative\n"
            "31001_1310, Freizeit\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert not result.is_valid
        finally:
            os.unlink(path)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_negative_section_adds_error(self):
        """Error when negative section exists but has no entries."""
        validator = InputValidator()
        content = (
            "#Filter positive\n"
            "31001_1000, Wohnhaus\n"
            "#Filter negative\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert not result.is_valid
        finally:
            os.unlink(path)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_orphan_lines_before_header_add_warning(self):
        """Warning for content lines that appear before any section header."""
        validator = InputValidator()
        content = (
            "31001_9999, orphan_line\n"
            "#Filter positive\n"
            "31001_1000, Wohnhaus\n"
            "#Filter negative\n"
            "31001_1310, Freizeit\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert len(result.warnings) > 0
        finally:
            os.unlink(path)

    @pytest.mark.unit
    def test_invalid_entry_format_adds_warning(self):
        """Warning when an entry does not match the ATKIS NNNNN_NNNN format."""
        validator = InputValidator()
        content = (
            "#Filter positive\n"
            "WRONGFORMAT, description\n"
            "#Filter negative\n"
            "31001_1310, Freizeit\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert len(result.warnings) > 0
        finally:
            os.unlink(path)

    @pytest.mark.unit
    def test_comments_and_empty_lines_are_ignored(self):
        """Comment lines (starting with #) and blank lines are not entries."""
        validator = InputValidator()
        content = (
            "# This is a top-level comment\n"
            "#Filter positive\n"
            "# another comment\n"
            "\n"
            "31001_1000, Wohnhaus\n"
            "#Filter negative\n"
            "31001_1310, Freizeit\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', encoding='utf-8', delete=False
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = ValidationResult()
            validator._check_filter_file(path, result)
            assert result.is_valid, f"Errors: {result.errors}"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestCheckOutputPaths — pure Python, no QGIS required
# ---------------------------------------------------------------------------

class TestCheckOutputPaths:
    """Tests for InputValidator._check_output_paths."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_output_path_adds_error(self):
        """Error when output path string is empty."""
        validator = InputValidator()
        result = ValidationResult()
        validator._check_output_paths("", "/some/workspace", result)
        assert not result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_workspace_path_adds_error(self):
        """Error when workspace path string is empty."""
        validator = InputValidator()
        result = ValidationResult()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "result.gpkg")
            validator._check_output_paths(output_path, "", result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_output_path_without_directory_adds_error(self):
        """Error when the output path does not include a directory."""
        validator = InputValidator()
        result = ValidationResult()
        validator._check_output_paths("output.gpkg", "/some/workspace", result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_non_gpkg_output_extension_adds_error(self):
        """Error when the output path does not end with .gpkg."""
        validator = InputValidator()
        result = ValidationResult()
        validator._check_output_paths(
            "C:/data/output.shp", "C:/workspace", result
        )
        assert not result.is_valid

    @pytest.mark.unit
    def test_valid_paths_no_errors(self):
        """No errors when output path is a full .gpkg path and workspace is set."""
        validator = InputValidator()
        result = ValidationResult()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "result.gpkg")
            validator._check_output_paths(output_path, tmpdir, result)
        assert result.is_valid, f"Errors: {result.errors}"


# ---------------------------------------------------------------------------
# TestCheckParams — requires QGIS (for QgsCoordinateReferenceSystem)
# ---------------------------------------------------------------------------

class TestCheckParams:
    """Tests for InputValidator._check_params."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_valid_params_no_errors(self):
        """No errors when all parameter values are within valid ranges."""
        params = {
            "min_overlap_blocks": "50.0",
            "global_footprint_density": "30.0",
            "min_area": "50.0",
            "min_bdg_count": "5",
            "min_patch_size": "1000.0",
            "max_hole_size": "5000.0",
            "max_gap_size": "2000.0",
        }
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert result.is_valid, f"Errors: {result.errors}"

    @pytest.mark.unit
    def test_non_numeric_value_adds_error(self):
        """Error when a numeric parameter has a non-numeric string value."""
        params = {"min_overlap_blocks": "not_a_number"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_value_below_minimum_adds_error(self):
        """Error when a parameter value is below its allowed minimum."""
        params = {"min_area": "5.0"}  # minimum is 10
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_value_above_maximum_adds_error(self):
        """Error when a parameter value exceeds its allowed maximum."""
        params = {"min_overlap_blocks": "150.0"}  # maximum is 100
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_invalid_crs_adds_error(self):
        """Error when spatial_reference_text is not a valid CRS identifier."""
        params = {"spatial_reference_text": "INVALID:9999"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_geographic_crs_adds_warning_not_error(self):
        """Warning (not error) when a geographic CRS is used instead of projected."""
        params = {"spatial_reference_text": "EPSG:4326"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert result.is_valid  # geographic CRS is a warning, not a blocking error
        assert len(result.warnings) > 0

    @pytest.mark.unit
    def test_partition_range_start_equals_end_adds_error(self):
        """Error when partition start equals partition end."""
        params = {"part_start": "5", "part_end": "5"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_partition_range_start_greater_than_end_adds_error(self):
        """Error when partition start is greater than partition end."""
        params = {"part_start": "10", "part_end": "3"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_partition_range_minus_one_means_all(self):
        """No error when part_start and part_end are both -1 (process all)."""
        params = {"part_start": "-1", "part_end": "-1"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert result.is_valid

    @pytest.mark.unit
    def test_partition_range_valid_start_less_than_end(self):
        """No error for a valid partition range (start < end)."""
        params = {"part_start": "1", "part_end": "10"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert result.is_valid

    @pytest.mark.unit
    def test_non_integer_partition_range_adds_error(self):
        """Error when part_start or part_end are not valid integers."""
        params = {"part_start": "abc", "part_end": "xyz"}
        result = ValidationResult()
        self.validator._check_params(params, result)
        assert not result.is_valid

    @pytest.mark.unit
    def test_empty_params_dict_no_errors(self):
        """No errors when params dict contains no known keys."""
        result = ValidationResult()
        self.validator._check_params({}, result)
        assert result.is_valid


# ---------------------------------------------------------------------------
# TestCheckValidityProcessing — integration (processing.run) / mocked fallback
# ---------------------------------------------------------------------------

class TestCheckValidityProcessing:
    """Tests for InputValidator._check_validity_processing."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_processing_exception_adds_warning_not_error(self):
        """If qgis:checkvalidity raises an exception, a warning is added and no crash occurs."""
        validator = InputValidator()
        with patch("helpers.check.processing.run", side_effect=Exception("QGIS unavailable")):
            layer = _make_polygon_layer()
            _add_polygon_feature(layer)
            result = ValidationResult()
            validator._check_validity_processing(layer, "TestLayer", result)
        # Must be a warning, not an error — processing failures are non-critical
        assert result.is_valid
        assert len(result.warnings) > 0

    @pytest.mark.integration
    def test_valid_layer_no_warning(self):
        """No warning for a layer with only geometrically valid polygons."""
        layer = _make_polygon_layer()
        _add_polygon_feature(layer)
        result = ValidationResult()
        self.validator._check_validity_processing(layer, "TestLayer", result)
        assert result.is_valid


# ---------------------------------------------------------------------------
# TestQuickPathCheck — unit tests (no QGIS layer operations)
# ---------------------------------------------------------------------------

class TestQuickPathCheck:
    """Tests for InputValidator.quick_path_check."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()

    @pytest.mark.unit
    def test_empty_string_returns_false(self):
        """An empty string path must return (False, message)."""
        ok, msg = self.validator.quick_path_check("")
        assert ok is False
        assert msg  # non-empty error message

    @pytest.mark.unit
    def test_whitespace_only_path_returns_false(self):
        """A whitespace-only string must be treated as empty."""
        ok, msg = self.validator.quick_path_check("   ")
        assert ok is False
        assert msg

    @pytest.mark.unit
    def test_nonexistent_path_returns_false(self):
        """A path that does not exist on disk must return (False, message)."""
        ok, msg = self.validator.quick_path_check("/nonexistent/path/that/does/not/exist")
        assert ok is False
        assert msg

    @pytest.mark.unit
    def test_existing_file_returns_true(self, tmp_path):
        """An existing file path with is_dir=False must return (True, '')."""
        f = tmp_path / "testfile.txt"
        f.write_text("x")
        ok, msg = self.validator.quick_path_check(str(f))
        assert ok is True
        assert msg == ""

    @pytest.mark.unit
    def test_existing_directory_with_is_dir_true_returns_true(self, tmp_path):
        """An existing directory path with is_dir=True must return (True, '')."""
        ok, msg = self.validator.quick_path_check(str(tmp_path), is_dir=True)
        assert ok is True
        assert msg == ""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_file_path_with_is_dir_true_returns_false(self, tmp_path):
        """A file path with is_dir=True must return (False, message) — it is not a directory."""
        f = tmp_path / "notadir.txt"
        f.write_text("x")
        ok, msg = self.validator.quick_path_check(str(f), is_dir=True)
        assert ok is False
        assert msg


# ---------------------------------------------------------------------------
# TestValidateAll — integration tests
# ---------------------------------------------------------------------------

class TestValidateAll:
    """Tests for InputValidator.validate_all."""

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()
        cls.validator = InputValidator()
        cls.crs = QgsCoordinateReferenceSystem("EPSG:25833")

    @pytest.mark.unit
    def test_all_empty_paths_produce_errors(self):
        """Calling validate_all with no paths at all must return errors for each layer."""
        result = self.validator.validate_all(
            hu_path="", rn_path="", part_path="", aux_path="",
            filter_path="", output_path="", workspace_path="",
            spatial_reference=self.crs,
        )
        assert not result.is_valid
        assert len(result.errors) >= 4  # at least one error per required layer

    @pytest.mark.unit
    def test_nonexistent_paths_produce_errors(self, tmp_path):
        """Non-existent file paths must each produce an error."""
        fake_path = str(tmp_path / "does_not_exist.shp")
        result = self.validator.validate_all(
            hu_path=fake_path, rn_path=fake_path,
            part_path=fake_path, aux_path=fake_path,
            filter_path="", output_path="", workspace_path="",
            spatial_reference=self.crs,
        )
        assert not result.is_valid
        # At least the four layer paths should produce errors
        assert len(result.errors) >= 4


# ---------------------------------------------------------------------------
# TestValidateAllChecksumCache — per-file skip logic
# ---------------------------------------------------------------------------

class TestValidateAllChecksumCache:
    """Tests for the checksum-based per-file skip logic in validate_all.

    `QgsVectorLayer` is patched to a stub so these tests exercise only the
    new orchestration logic (which checks run vs. are skipped, and how the
    returned `layer_cache` is threaded through), not the already-covered
    individual `_check_*` methods.
    """

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()

    @staticmethod
    def _make_paths(tmp_path):
        """Create 5 placeholder files for the 5 checkable inputs."""
        paths = {}
        for field in ("HuPath", "RnPath", "PartPath", "AuxPath", "FilterPath"):
            p = tmp_path / f"{field}.gpkg"
            p.write_text("placeholder", encoding="utf-8")
            paths[field] = str(p)
        return paths

    @staticmethod
    def _make_mock_layer(crs_authid="EPSG:25833"):
        layer = MagicMock()
        layer.isValid.return_value = True
        layer.crs.return_value.authid.return_value = crs_authid
        layer.featureCount.return_value = 0
        return layer

    def _patched_layer(self, crs_authid="EPSG:25833"):
        """Context-manager-friendly patch target for `helpers.check.QgsVectorLayer`."""
        return patch("helpers.check.QgsVectorLayer",
                     side_effect=lambda *a, **k: self._make_mock_layer(crs_authid))

    @pytest.mark.unit
    def test_first_call_runs_all_content_checks_and_populates_cache(self, tmp_path):
        """With no previous_cache, every content check runs and layer_cache is filled."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        checksums = {k: f"cs_{k}" for k in paths}

        with self._patched_layer(), \
             patch.object(validator, "_check_geometries") as mock_geom, \
             patch.object(validator, "_check_validity_processing") as mock_valid, \
             patch.object(validator, "_check_hu_layer") as mock_hu, \
             patch.object(validator, "_check_rn_layer") as mock_rn, \
             patch.object(validator, "_check_aux_layer") as mock_aux, \
             patch.object(validator, "_check_part_layer") as mock_part, \
             patch.object(validator, "_check_multipart_lines") as mock_multi, \
             patch.object(validator, "_check_filter_file") as mock_filter:
            result = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs,
                file_checksums=checksums,
            )

        assert mock_geom.call_count == 4
        assert mock_valid.call_count == 4
        mock_hu.assert_called_once()
        mock_rn.assert_called_once()
        mock_aux.assert_called_once()
        mock_part.assert_called_once()
        assert mock_multi.call_count == 2  # RN + Aux only
        mock_filter.assert_called_once()
        assert set(result.layer_cache) == set(paths)
        for field, checksum in checksums.items():
            assert result.layer_cache[field]["checksum"] == checksum

    @pytest.mark.unit
    def test_unchanged_checksums_skip_all_content_checks(self, tmp_path):
        """A second call with unchanged checksums must not re-run content checks,
        but cheap checks (CRS, feature counts, params) run again every time."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        checksums = {k: f"cs_{k}" for k in paths}

        with self._patched_layer(), \
             patch.object(validator, "_check_geometries") as mock_geom, \
             patch.object(validator, "_check_validity_processing"), \
             patch.object(validator, "_check_hu_layer") as mock_hu, \
             patch.object(validator, "_check_rn_layer"), \
             patch.object(validator, "_check_aux_layer"), \
             patch.object(validator, "_check_part_layer"), \
             patch.object(validator, "_check_multipart_lines"), \
             patch.object(validator, "_check_filter_file") as mock_filter, \
             patch.object(validator, "_check_crs") as mock_crs, \
             patch.object(validator, "_check_feature_counts") as mock_counts, \
             patch.object(validator, "_check_params") as mock_params:
            first = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, params={"a": 1},
                file_checksums=checksums,
            )
            second = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, params={"a": 1},
                file_checksums=checksums,
                previous_cache=first.layer_cache,
            )

        # Content checks ran exactly once (during the first call)
        assert mock_geom.call_count == 4
        mock_hu.assert_called_once()
        mock_filter.assert_called_once()
        # Cheap checks re-run on every call
        assert mock_crs.call_count == 8  # 4 layers x 2 calls
        assert mock_counts.call_count == 2
        assert mock_params.call_count == 2
        assert second.layer_cache == first.layer_cache

    @pytest.mark.unit
    def test_changed_checksum_only_rechecks_that_file(self, tmp_path):
        """Only the file whose checksum changed gets its content re-checked."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        checksums = {k: f"cs_{k}" for k in paths}

        with self._patched_layer(), \
             patch.object(validator, "_check_geometries") as mock_geom, \
             patch.object(validator, "_check_validity_processing"), \
             patch.object(validator, "_check_hu_layer") as mock_hu, \
             patch.object(validator, "_check_rn_layer") as mock_rn, \
             patch.object(validator, "_check_aux_layer") as mock_aux, \
             patch.object(validator, "_check_part_layer") as mock_part, \
             patch.object(validator, "_check_multipart_lines"), \
             patch.object(validator, "_check_filter_file"):
            first = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, file_checksums=checksums,
            )
            changed = dict(checksums)
            changed["HuPath"] = "cs_HuPath_v2"  # simulate an edited HU file
            validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, file_checksums=changed,
                previous_cache=first.layer_cache,
            )

        assert mock_hu.call_count == 2   # HU re-checked both times
        assert mock_rn.call_count == 1   # RN, Part, Aux only checked once
        assert mock_part.call_count == 1
        assert mock_aux.call_count == 1
        assert mock_geom.call_count == 5  # 4 (first call) + 1 (HU on second call)

    @pytest.mark.unit
    def test_crs_change_alone_does_not_trigger_content_recheck(self, tmp_path):
        """Fixing the target CRS re-evaluates the CRS-mismatch error without
        re-scanning unchanged files — the exact scenario this cache exists for."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        checksums = {k: f"cs_{k}" for k in paths}

        with self._patched_layer(crs_authid="EPSG:25832"), \
             patch.object(validator, "_check_geometries") as mock_geom, \
             patch.object(validator, "_check_validity_processing"), \
             patch.object(validator, "_check_hu_layer"), \
             patch.object(validator, "_check_rn_layer"), \
             patch.object(validator, "_check_aux_layer"), \
             patch.object(validator, "_check_part_layer"), \
             patch.object(validator, "_check_multipart_lines"), \
             patch.object(validator, "_check_filter_file"):
            wrong_crs = QgsCoordinateReferenceSystem("EPSG:25833")  # layer is 25832
            first = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=wrong_crs, file_checksums=checksums,
            )
            assert any("CRS mismatch" in e for e in first.errors)

            fixed_crs = QgsCoordinateReferenceSystem("EPSG:25832")  # now matches
            second = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=fixed_crs, file_checksums=checksums,
                previous_cache=first.layer_cache,
            )

        assert not any("CRS mismatch" in e for e in second.errors), (
            "CRS error must be gone once the target CRS matches, even though "
            "the files themselves were not re-scanned"
        )
        assert mock_geom.call_count == 4, \
            "Content checks must not re-run just because the target CRS changed"

    @pytest.mark.unit
    def test_reused_content_errors_and_warnings_reappear_in_result(self, tmp_path):
        """Errors/warnings from a skipped content check are still reported."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        checksums = {k: f"cs_{k}" for k in paths}

        def _hu_side_effect(_layer, result):
            result.add_error("HU content error")

        with self._patched_layer(), \
             patch.object(validator, "_check_geometries"), \
             patch.object(validator, "_check_validity_processing"), \
             patch.object(validator, "_check_hu_layer", side_effect=_hu_side_effect), \
             patch.object(validator, "_check_rn_layer"), \
             patch.object(validator, "_check_aux_layer"), \
             patch.object(validator, "_check_part_layer"), \
             patch.object(validator, "_check_multipart_lines"), \
             patch.object(validator, "_check_filter_file"):
            first = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, file_checksums=checksums,
            )
            second = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, file_checksums=checksums,
                previous_cache=first.layer_cache,
            )

        assert "HU content error" in first.errors
        assert "HU content error" in second.errors, \
            "A reused (skipped) content check's error must still be reported"

    @pytest.mark.unit
    def test_no_checksums_never_hits_cache(self, tmp_path):
        """Without file_checksums, every call runs full content checks (back-compat)."""
        paths = self._make_paths(tmp_path)
        validator = InputValidator()
        crs = QgsCoordinateReferenceSystem("EPSG:25833")

        with self._patched_layer(), \
             patch.object(validator, "_check_geometries") as mock_geom, \
             patch.object(validator, "_check_validity_processing"), \
             patch.object(validator, "_check_hu_layer"), \
             patch.object(validator, "_check_rn_layer"), \
             patch.object(validator, "_check_aux_layer"), \
             patch.object(validator, "_check_part_layer"), \
             patch.object(validator, "_check_multipart_lines"), \
             patch.object(validator, "_check_filter_file"):
            first = validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs,
            )
            validator.validate_all(
                hu_path=paths["HuPath"], rn_path=paths["RnPath"],
                part_path=paths["PartPath"], aux_path=paths["AuxPath"],
                filter_path=paths["FilterPath"],
                output_path="", workspace_path="",
                spatial_reference=crs, previous_cache=first.layer_cache,
            )

        assert mock_geom.call_count == 8  # 4 per call, no skip without checksums
        assert first.layer_cache == {}
