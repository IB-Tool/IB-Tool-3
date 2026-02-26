"""
Smoke tests for helpers/qgis_defaults.py — QGISDefaults dataclass.

Coverage:
- Module imports without error
- QGISDefaults instantiates with expected default values
- All fields have correct types
- Instance is mutable (dataclass allows overrides)
"""

import pytest

from helpers.qgis_defaults import QGISDefaults


class TestQGISDefaults:
    """Smoke tests for the QGISDefaults dataclass."""

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_instantiates_without_arguments(self):
        """QGISDefaults() can be constructed without arguments."""
        defaults = QGISDefaults()
        assert defaults is not None

    # ------------------------------------------------------------------
    # Default values match project spec
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_buffer_segments_default(self):
        """buffer_segments default is 5."""
        assert QGISDefaults().buffer_segments == 5

    @pytest.mark.unit
    def test_buffer_end_cap_style_default(self):
        """buffer_end_cap_style default is 0 (round)."""
        assert QGISDefaults().buffer_end_cap_style == 0

    @pytest.mark.unit
    def test_buffer_join_style_default(self):
        """buffer_join_style default is 0 (round)."""
        assert QGISDefaults().buffer_join_style == 0

    @pytest.mark.unit
    def test_buffer_miter_limit_default(self):
        """buffer_miter_limit default is 2.0."""
        assert QGISDefaults().buffer_miter_limit == 2.0

    @pytest.mark.unit
    def test_coordinate_precision_default(self):
        """coordinate_precision default is 0."""
        assert QGISDefaults().coordinate_precision == 0

    @pytest.mark.unit
    def test_temp_layer_prefix_default(self):
        """temp_layer_prefix default is 'temp'."""
        assert QGISDefaults().temp_layer_prefix == "temp"

    # ------------------------------------------------------------------
    # Type correctness
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_integer_fields_are_int(self):
        """buffer_segments, buffer_end_cap_style, buffer_join_style, coordinate_precision are int."""
        d = QGISDefaults()
        assert isinstance(d.buffer_segments, int)
        assert isinstance(d.buffer_end_cap_style, int)
        assert isinstance(d.buffer_join_style, int)
        assert isinstance(d.coordinate_precision, int)

    @pytest.mark.unit
    def test_float_field_is_float(self):
        """buffer_miter_limit is float."""
        assert isinstance(QGISDefaults().buffer_miter_limit, float)

    @pytest.mark.unit
    def test_string_field_is_str(self):
        """temp_layer_prefix is str."""
        assert isinstance(QGISDefaults().temp_layer_prefix, str)

    # ------------------------------------------------------------------
    # Mutability (dataclass allows field overrides)
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_fields_can_be_overridden_at_construction(self):
        """Fields accept custom values when passed to the constructor."""
        custom = QGISDefaults(buffer_segments=10, temp_layer_prefix="custom_tmp")
        assert custom.buffer_segments == 10
        assert custom.temp_layer_prefix == "custom_tmp"

    @pytest.mark.unit
    def test_default_instance_is_independent_of_custom_instance(self):
        """Overriding fields in one instance does not affect a default instance."""
        custom = QGISDefaults(buffer_segments=99)
        default = QGISDefaults()
        assert default.buffer_segments == 5
        assert custom.buffer_segments == 99