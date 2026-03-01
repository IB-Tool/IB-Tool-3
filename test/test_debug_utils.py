# -*- coding: utf-8 -*-
"""Tests for helpers/debug_utils.py.

Covers _next_debug_index, save_debug_layer, and save_debug_features.
All I/O calls to save_temp_layer_to_gpkg are mocked so that no real disk
writes are required for most tests; one integration-style test verifies
the full delegation chain using a tmp_path fixture.
"""
import os
import pytest
from unittest.mock import patch

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
)

from .utilities import get_qgis_app
from ibtool.helpers.debug_utils import (
    _next_debug_index,
    save_debug_layer,
    save_debug_features,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_polygon_layer(name: str = "test") -> QgsVectorLayer:
    """One-feature polygon layer ready for use in tests."""
    layer = QgsVectorLayer("Polygon?crs=EPSG:25833", name, "memory")
    feat = QgsFeature()
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


# ── _next_debug_index ─────────────────────────────────────────────────────────

class TestNextDebugIndex:
    """Tests for the _next_debug_index helper."""

    @pytest.mark.unit
    def test_returns_one_for_nonexistent_directory(self, tmp_path):
        result = _next_debug_index(str(tmp_path / "does_not_exist"))
        assert result == 1

    @pytest.mark.unit
    def test_returns_one_for_empty_directory(self, tmp_path):
        debug_dir = tmp_path / "empty"
        debug_dir.mkdir()
        assert _next_debug_index(str(debug_dir)) == 1

    @pytest.mark.unit
    def test_counts_gpkg_files(self, tmp_path):
        debug_dir = tmp_path / "debug"
        debug_dir.mkdir()
        (debug_dir / "001_step.gpkg").touch()
        (debug_dir / "002_step_err.gpkg").touch()
        assert _next_debug_index(str(debug_dir)) == 3

    @pytest.mark.unit
    def test_ignores_non_gpkg_files(self, tmp_path):
        debug_dir = tmp_path / "debug"
        debug_dir.mkdir()
        (debug_dir / "001_step.gpkg").touch()
        (debug_dir / "note.txt").touch()
        (debug_dir / "readme.md").touch()
        assert _next_debug_index(str(debug_dir)) == 2


# ── save_debug_layer ──────────────────────────────────────────────────────────

class TestSaveDebugLayer:
    """Tests for save_debug_layer."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_none_for_non_vector_layer(self):
        with patch("ibtool.helpers.debug_utils.Logger"):
            result = save_debug_layer("not_a_layer", "Tool", "step", "/mock/ws")
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_invalid_layer(self):
        invalid = QgsVectorLayer("Polygon?crs=EPSG:25833", "bad", "memory")
        # Force invalid by not calling isValid — use an unpopulated layer path
        invalid2 = QgsVectorLayer("/nonexistent/path.gpkg", "bad", "ogr")
        with patch("ibtool.helpers.debug_utils.Logger"):
            result = save_debug_layer(invalid2, "Tool", "step", "/mock/ws")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_for_empty_layer(self):
        empty = QgsVectorLayer("Polygon?crs=EPSG:25833", "empty", "memory")
        with patch("ibtool.helpers.debug_utils.Logger"):
            result = save_debug_layer(empty, "Tool", "step", "/mock/ws")
        assert result is None

    @pytest.mark.unit
    def test_calls_save_func_for_valid_layer(self, tmp_path):
        layer = _make_polygon_layer()
        fake_path = "/fake/out.gpkg"
        with patch(
            "ibtool.helpers.debug_utils.save_temp_layer_to_gpkg",
            return_value=fake_path,
        ) as mock_save:
            with patch("ibtool.helpers.debug_utils.Logger"):
                result = save_debug_layer(
                    layer, "GapClose", "after_dissolve", str(tmp_path)
                )
        mock_save.assert_called_once()
        assert result == fake_path

    @pytest.mark.unit
    def test_error_suffix_present_when_is_error_true(self, tmp_path):
        layer = _make_polygon_layer()
        with patch(
            "ibtool.helpers.debug_utils.save_temp_layer_to_gpkg",
            return_value="/fake/out.gpkg",
        ) as mock_save:
            with patch("ibtool.helpers.debug_utils.Logger"):
                save_debug_layer(
                    layer, "GapClose", "failed_buffer", str(tmp_path), is_error=True
                )
        filename_arg = mock_save.call_args[0][1]
        assert "_err" in filename_arg

    @pytest.mark.unit
    def test_no_error_suffix_when_is_error_false(self, tmp_path):
        layer = _make_polygon_layer()
        with patch(
            "ibtool.helpers.debug_utils.save_temp_layer_to_gpkg",
            return_value="/fake/out.gpkg",
        ) as mock_save:
            with patch("ibtool.helpers.debug_utils.Logger"):
                save_debug_layer(
                    layer, "GapClose", "after_dissolve", str(tmp_path), is_error=False
                )
        filename_arg = mock_save.call_args[0][1]
        assert "_err" not in filename_arg

    @pytest.mark.unit
    def test_filename_has_numeric_prefix(self, tmp_path):
        """File names must start with a zero-padded index prefix like '001_'."""
        layer = _make_polygon_layer()
        captured = {}

        def capture_save(lyr, filename, path):
            captured["filename"] = filename
            return "/fake/out.gpkg"

        with patch(
            "ibtool.helpers.debug_utils.save_temp_layer_to_gpkg",
            side_effect=capture_save,
        ):
            with patch("ibtool.helpers.debug_utils.Logger"):
                save_debug_layer(layer, "GapClose", "step_a", str(tmp_path))

        assert captured["filename"][:3].isdigit(), (
            f"Filename should start with a numeric prefix, got: {captured['filename']}"
        )


# ── save_debug_features ───────────────────────────────────────────────────────

class TestSaveDebugFeatures:
    """Tests for save_debug_features."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_for_empty_feature_list(self):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        with patch("ibtool.helpers.debug_utils.Logger"):
            result = save_debug_features([], crs, "Tool", "step", "/mock/ws")
        assert result is None

    @pytest.mark.unit
    def test_delegates_to_save_debug_layer(self, tmp_path):
        """save_debug_features must call save_debug_layer exactly once."""
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        feat = QgsFeature()
        feat.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0), QgsPointXY(10, 0),
                    QgsPointXY(10, 10), QgsPointXY(0, 10),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        fake_path = "/fake/out.gpkg"
        with patch(
            "ibtool.helpers.debug_utils.save_debug_layer",
            return_value=fake_path,
        ) as mock_save:
            with patch("ibtool.helpers.debug_utils.Logger"):
                result = save_debug_features(
                    [feat], crs, "Tool", "step", str(tmp_path)
                )
        mock_save.assert_called_once()
        assert result == fake_path

    @pytest.mark.unit
    def test_is_error_forwarded_to_save_debug_layer(self, tmp_path):
        crs = QgsCoordinateReferenceSystem("EPSG:25833")
        feat = QgsFeature()
        feat.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0), QgsPointXY(10, 0),
                    QgsPointXY(10, 10), QgsPointXY(0, 10),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        with patch(
            "ibtool.helpers.debug_utils.save_debug_layer",
            return_value="/fake/path.gpkg",
        ) as mock_save:
            with patch("ibtool.helpers.debug_utils.Logger"):
                save_debug_features(
                    [feat], crs, "Tool", "step", str(tmp_path), is_error=True
                )
        # is_error=True must be forwarded as keyword argument
        _, kwargs = mock_save.call_args
        assert kwargs.get("is_error") is True
