"""
Tests for ibtool_tools/ImportFilter.py.

The module exposes two public functions:

  import_filter(filename, HU_Input)
    - reads a text filter file → returns (filterpos, filterneg, fieldname)

  input_hu_filter(HU_Input, filter_file, MinAreaAllBdgs, ...)
    - applies import_filter to build filter strings, runs QGIS Processing

Unit tests cover (import_filter — no Processing needed):
  - missing file → raises Exception
  - invalid layer → raises Exception
  - layer without 'fkt'/'funktion' field → raises Exception
  - valid file + 'fkt' field → correct filter strings returned
  - valid file + 'funktion' field → 'funktion' is used as fieldname
  - filter string format is correct (fieldname LIKE 'value' OR …)
  - empty filter sections → empty strings returned

Integration tests cover (input_hu_filter):
  - building count below MinAreaAllBdgs → returns HU_Input unchanged
  - invalid layer → raises Exception
"""

import os
import textwrap
import pytest
from pathlib import Path
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsWkbTypes,
)
from PyQt5.QtCore import QVariant

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.ibtool_tools.ImportFilter import import_filter, input_hu_filter


# ---------------------------------------------------------------------------
# Geometry / layer factory helpers
# ---------------------------------------------------------------------------

def _polygon_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Empty in-memory polygon layer."""
    return QgsVectorLayer(f"Polygon?crs={crs}", "test", "memory")


def _polygon_layer_with_field(field_name: str, crs: str = "EPSG:25833") -> QgsVectorLayer:
    """In-memory polygon layer with a single string field."""
    layer = _polygon_layer(crs)
    layer.dataProvider().addAttributes([QgsField(field_name, QVariant.String)])
    layer.updateFields()
    return layer


def _add_square(layer: QgsVectorLayer, x0: float, y0: float, size: float):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolygonXY([[
        QgsPointXY(x0,        y0),
        QgsPointXY(x0 + size, y0),
        QgsPointXY(x0 + size, y0 + size),
        QgsPointXY(x0,        y0 + size),
        QgsPointXY(x0,        y0),
    ]]))
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()


def _write_filter_file(path: Path, positive: list, negative: list) -> str:
    """Write a filter file and return its path as a string."""
    lines = ["#Filter positive"] + positive + ["#Filter negative"] + negative
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# TestImportFilter — unit tests (no QGIS Processing algorithms required)
# ---------------------------------------------------------------------------

class TestImportFilter:
    """Unit tests for ImportFilter.import_filter."""

    # --- error conditions ---

    @pytest.mark.unit
    def test_missing_file_raises_exception(self, tmp_path):
        """A file that does not exist must raise Exception."""
        non_existent = str(tmp_path / "does_not_exist.txt")
        layer = _polygon_layer_with_field("fkt")

        with pytest.raises(Exception, match="existiert nicht"):
            import_filter(non_existent, layer)

    @pytest.mark.unit
    def test_invalid_layer_raises_exception(self, tmp_path):
        """An uninitialised (invalid) layer must raise Exception."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], ["9999"])
        invalid_layer = QgsVectorLayer()

        with pytest.raises(Exception):
            import_filter(filter_path, invalid_layer)

    @pytest.mark.unit
    def test_non_polygon_layer_raises_exception(self, tmp_path):
        """A line layer instead of polygon layer must raise Exception."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        line_layer = QgsVectorLayer("LineString?crs=EPSG:25833", "lines", "memory")

        with pytest.raises(Exception):
            import_filter(filter_path, line_layer)

    @pytest.mark.unit
    def test_missing_fkt_and_funktion_field_raises_exception(self, tmp_path):
        """Layer without 'fkt' or 'funktion' field must raise Exception."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        layer = _polygon_layer()   # no fkt/funktion field

        with pytest.raises(Exception, match="weder.*fkt.*funktion"):
            import_filter(filter_path, layer)

    # --- correct behaviour ---

    @pytest.mark.unit
    def test_fkt_field_is_selected_when_present(self, tmp_path):
        """'fkt' field is used when both 'fkt' and 'funktion' exist."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        layer = _polygon_layer_with_field("fkt")

        _filterpos, _filterneg, fieldname = import_filter(filter_path, layer)

        assert fieldname == "fkt"

    @pytest.mark.unit
    def test_funktion_field_used_when_fkt_absent(self, tmp_path):
        """'funktion' is used when 'fkt' field is absent."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        layer = _polygon_layer_with_field("funktion")

        _filterpos, _filterneg, fieldname = import_filter(filter_path, layer)

        assert fieldname == "funktion"

    @pytest.mark.unit
    def test_positive_filter_string_format(self, tmp_path):
        """Positive filter string must have format 'fkt LIKE '1010' OR fkt LIKE '2020''."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010", "2020"], [])
        layer = _polygon_layer_with_field("fkt")

        filterpos, _filterneg, _fieldname = import_filter(filter_path, layer)

        assert "fkt LIKE '1010'" in filterpos
        assert "fkt LIKE '2020'" in filterpos

    @pytest.mark.unit
    def test_negative_filter_string_format(self, tmp_path):
        """Negative filter string must reference the correct field and values."""
        filter_path = _write_filter_file(tmp_path / "f.txt", [], ["9999"])
        layer = _polygon_layer_with_field("fkt")

        _filterpos, filterneg, _fieldname = import_filter(filter_path, layer)

        assert "fkt LIKE '9999'" in filterneg

    @pytest.mark.unit
    def test_empty_sections_return_empty_strings(self, tmp_path):
        """Filter file with no codes returns empty filter strings."""
        # file with only section headers, no codes
        filter_path = _write_filter_file(tmp_path / "f.txt", [], [])
        layer = _polygon_layer_with_field("fkt")

        filterpos, filterneg, fieldname = import_filter(filter_path, layer)

        assert filterpos == ""
        assert filterneg == ""
        assert fieldname == "fkt"

    @pytest.mark.unit
    def test_codes_are_truncated_to_10_characters(self, tmp_path):
        """Only the first 10 characters of each code line are used."""
        long_code = "1234567890EXTRA"  # 15 chars → should become '1234567890'
        filter_path = _write_filter_file(tmp_path / "f.txt", [long_code], [])
        layer = _polygon_layer_with_field("fkt")

        filterpos, _filterneg, _fieldname = import_filter(filter_path, layer)

        assert "'1234567890'" in filterpos
        assert "EXTRA" not in filterpos

    @pytest.mark.unit
    def test_multiple_positive_codes_joined_with_or(self, tmp_path):
        """Multiple positive codes must be joined with ' OR '."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["A", "B", "C"], [])
        layer = _polygon_layer_with_field("fkt")

        filterpos, _filterneg, _fieldname = import_filter(filter_path, layer)

        # Should contain exactly 2 OR operators for 3 values
        assert filterpos.count(" OR ") == 2

    @pytest.mark.unit
    def test_single_code_has_no_trailing_or(self, tmp_path):
        """A single code must not end with ' OR '."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        layer = _polygon_layer_with_field("fkt")

        filterpos, _filterneg, _fieldname = import_filter(filter_path, layer)

        assert not filterpos.endswith(" OR ")


# ---------------------------------------------------------------------------
# TestInputHuFilter — integration tests
# ---------------------------------------------------------------------------

class TestInputHuFilter:
    """Tests for ImportFilter.input_hu_filter."""

    CRS_ID = "EPSG:25833"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_too_few_buildings_returns_input_unchanged(self, tmp_path):
        """When building count ≤ MinAreaAllBdgs, HU_Input is returned unchanged."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], ["9999"])
        layer = _polygon_layer_with_field("fkt", self.CRS_ID)
        _add_square(layer, 0, 0, 50)    # 1 feature only

        # MinAreaAllBdgs default is 56.8; with 1 feature the condition is not met
        result = input_hu_filter(layer, filter_path, MinAreaAllBdgs=100)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        # With 1 building ≤ 100 threshold → returns input unchanged
        assert result.featureCount() == layer.featureCount()

    @pytest.mark.integration
    def test_invalid_layer_raises_exception(self, tmp_path):
        """Invalid polygon layer must raise Exception."""
        filter_path = _write_filter_file(tmp_path / "f.txt", ["1010"], [])
        invalid_layer = QgsVectorLayer()

        with pytest.raises(Exception):
            input_hu_filter(invalid_layer, filter_path)
