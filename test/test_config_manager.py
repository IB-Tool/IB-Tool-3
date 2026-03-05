"""
Tests for helpers/config_manager.py — ConfigManager and config dataclasses.

Coverage:
- Default values of all four dataclasses
- ConfigManager init (no file, existing file)
- load_config / save_config roundtrip
- Partial INI file (missing sections use defaults)
- load_config raises FileNotFoundError for missing file
- create_example_config creates a loadable file
- update_config changes values, ignores unknown keys
- validate_paths / get_missing_paths
- config_exists
- apply_to_ui_elements
- get_effective_output_directory / get_effective_log_directory
- get_processing_parameters
"""

import os
import tempfile
import pytest

from .utilities import get_qgis_app

# QGIS must be available before importing config_manager (it imports QgsVectorLayer)
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from helpers.config_manager import (
    ConfigManager,
    InputDataConfig,
    ProcessingConfig,
    OutputConfig,
    UIConfig,
    PluginConfig,
    ValidationCacheConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmpdir: str) -> ConfigManager:
    """Create a ConfigManager pointing to a temp directory (no CONFIG.ini)."""
    return ConfigManager(tmpdir)


def _write_ini(tmpdir: str, content: str) -> str:
    """Write content to CONFIG.ini in tmpdir, return path."""
    path = os.path.join(tmpdir, "CONFIG.ini")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# TestConfigDataclasses — pure dataclass defaults, no QGIS layer operations
# ---------------------------------------------------------------------------

class TestConfigDataclasses:
    """Tests that dataclass default values are correct."""

    @pytest.mark.unit
    def test_input_data_config_defaults_are_empty_strings(self):
        cfg = InputDataConfig()
        assert cfg.building_footprints_path == ""
        assert cfg.road_network_path == ""
        assert cfg.partitions_path == ""
        assert cfg.aux_layer_path == ""
        assert cfg.filter_file_path == ""

    @pytest.mark.unit
    def test_processing_config_numeric_defaults(self):
        cfg = ProcessingConfig()
        assert cfg.road_length_threshold == 50.0
        assert cfg.coordinate_tolerance == 0.0001
        assert cfg.buffer_distance == 5.0
        assert cfg.grid_size == 100.0
        assert cfg.min_building_count == 5
        assert cfg.density_threshold == 0.3
        assert cfg.min_cluster_size == 3
        assert cfg.max_distance == 200.0
        assert cfg.crs_epsg == 25832
        assert cfg.output_format == "gpkg"

    @pytest.mark.unit
    def test_processing_config_partition_defaults(self):
        cfg = ProcessingConfig()
        assert cfg.part_start == 1
        assert cfg.part_end == -1   # -1 means process all
        assert cfg.part_list == ""

    @pytest.mark.unit
    def test_processing_config_debug_defaults(self):
        cfg = ProcessingConfig()
        assert cfg.debug_mode is False
        assert cfg.delete_part_log is True

    @pytest.mark.unit
    def test_output_config_defaults(self):
        cfg = OutputConfig()
        assert cfg.output_prefix == "ibtool_result"
        assert cfg.auto_save is True
        assert cfg.add_to_map is True
        assert cfg.overwrite_existing is False

    @pytest.mark.unit
    def test_ui_config_defaults(self):
        cfg = UIConfig()
        assert cfg.auto_load_last_used is True
        assert cfg.show_progress_details is True
        assert cfg.log_level == "INFO"
        assert cfg.remember_window_size is True


# ---------------------------------------------------------------------------
# TestConfigManagerInit
# ---------------------------------------------------------------------------

class TestConfigManagerInit:
    """Tests for ConfigManager initialization."""

    @pytest.mark.unit
    def test_init_creates_default_config_without_ini_file(self):
        """Manager starts with valid default config when no CONFIG.ini exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            cfg = mgr.get_config()
            assert isinstance(cfg, PluginConfig)
            assert isinstance(cfg.input_data, InputDataConfig)
            assert isinstance(cfg.processing, ProcessingConfig)
            assert isinstance(cfg.output, OutputConfig)
            assert isinstance(cfg.ui, UIConfig)

    @pytest.mark.unit
    def test_init_sets_config_file_path_correctly(self):
        """config_file_path is set to <plugin_root>/CONFIG.ini."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            assert mgr.config_file_path == os.path.join(tmpdir, "CONFIG.ini")

    @pytest.mark.unit
    def test_default_workspace_is_under_home_directory(self):
        """Default workspace_directory is inside the user home directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            home = os.path.expanduser("~")
            assert mgr.config.output.workspace_directory.startswith(home)

    @pytest.mark.unit
    def test_default_log_directory_is_inside_plugin_root(self):
        """Default log_directory is <plugin_root>/logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            assert mgr.config.ui.log_directory == os.path.join(tmpdir, "logs")

    @pytest.mark.unit
    def test_config_exists_returns_false_when_no_file(self):
        """config_exists() is False when CONFIG.ini has not been created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            assert mgr.config_exists() is False

    @pytest.mark.unit
    def test_init_loads_existing_config_file_automatically(self):
        """If CONFIG.ini exists at init time, values are loaded from it."""
        content = (
            "[PROCESSING]\n"
            "road_length_threshold = 99.0\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.processing.road_length_threshold == 99.0


# ---------------------------------------------------------------------------
# TestConfigManagerLoadConfig
# ---------------------------------------------------------------------------

class TestConfigManagerLoadConfig:
    """Tests for ConfigManager.load_config()."""

    @pytest.mark.unit
    def test_load_raises_for_missing_file(self):
        """load_config() raises FileNotFoundError when CONFIG.ini is absent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            with pytest.raises(FileNotFoundError):
                mgr.load_config()

    @pytest.mark.unit
    def test_load_input_data_section(self):
        """[INPUT_DATA] section is read and stored correctly."""
        content = (
            "[INPUT_DATA]\n"
            "building_footprints_path = /data/buildings.shp\n"
            "road_network_path = /data/roads.shp\n"
            "partitions_path = /data/parts.shp\n"
            "aux_layer_path = /data/aux.shp\n"
            "filter_file_path = /data/filter.txt\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.input_data.building_footprints_path == "/data/buildings.shp"
            assert mgr.config.input_data.road_network_path == "/data/roads.shp"
            assert mgr.config.input_data.partitions_path == "/data/parts.shp"
            assert mgr.config.input_data.aux_layer_path == "/data/aux.shp"
            assert mgr.config.input_data.filter_file_path == "/data/filter.txt"

    @pytest.mark.unit
    def test_load_processing_section_floats_and_ints(self):
        """Numeric fields in [PROCESSING] are parsed as the correct types."""
        content = (
            "[PROCESSING]\n"
            "road_length_threshold = 75.5\n"
            "min_building_count = 10\n"
            "crs_epsg = 25833\n"
            "output_format = shp\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.processing.road_length_threshold == 75.5
            assert mgr.config.processing.min_building_count == 10
            assert mgr.config.processing.crs_epsg == 25833
            assert mgr.config.processing.output_format == "shp"

    @pytest.mark.unit
    def test_load_processing_boolean_fields(self):
        """Boolean fields (debug_mode, delete_part_log) are parsed correctly."""
        content = (
            "[PROCESSING]\n"
            "debug_mode = True\n"
            "delete_part_log = False\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.processing.debug_mode is True
            assert mgr.config.processing.delete_part_log is False

    @pytest.mark.unit
    def test_load_output_section(self):
        """[OUTPUT] section fields are read correctly."""
        content = (
            "[OUTPUT]\n"
            "workspace_directory = /ws\n"
            "output_directory = /out\n"
            "output_prefix = myresult\n"
            "auto_save = False\n"
            "add_to_map = False\n"
            "overwrite_existing = True\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.output.workspace_directory == "/ws"
            assert mgr.config.output.output_directory == "/out"
            assert mgr.config.output.output_prefix == "myresult"
            assert mgr.config.output.auto_save is False
            assert mgr.config.output.overwrite_existing is True

    @pytest.mark.unit
    def test_load_ui_section(self):
        """[UI] section fields are read correctly."""
        content = (
            "[UI]\n"
            "auto_load_last_used = False\n"
            "log_level = WARNING\n"
            "log_directory = /logs\n"
            "remember_window_size = False\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.ui.auto_load_last_used is False
            assert mgr.config.ui.log_level == "WARNING"
            assert mgr.config.ui.log_directory == "/logs"
            assert mgr.config.ui.remember_window_size is False

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_partial_ini_keeps_defaults_for_missing_sections(self):
        """Sections absent from CONFIG.ini keep their default values."""
        content = "[PROCESSING]\nroad_length_threshold = 42.0\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            # Changed field:
            assert mgr.config.processing.road_length_threshold == 42.0
            # Untouched field from the same section:
            assert mgr.config.processing.buffer_distance == 5.0
            # Section not in file — default applies:
            assert mgr.config.input_data.building_footprints_path == ""

    @pytest.mark.unit
    def test_load_partition_range_fields(self):
        """part_start, part_end and part_list are loaded from PROCESSING."""
        content = (
            "[PROCESSING]\n"
            "part_start = 3\n"
            "part_end = 10\n"
            "part_list = PART_3,PART_5\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.processing.part_start == 3
            assert mgr.config.processing.part_end == 10
            assert mgr.config.processing.part_list == "PART_3,PART_5"


# ---------------------------------------------------------------------------
# TestConfigManagerSaveConfig
# ---------------------------------------------------------------------------

class TestConfigManagerSaveConfig:
    """Tests for ConfigManager.save_config()."""

    @pytest.mark.unit
    def test_save_creates_config_ini_file(self):
        """save_config() writes CONFIG.ini to the plugin root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.save_config()
            assert os.path.exists(os.path.join(tmpdir, "CONFIG.ini"))

    @pytest.mark.unit
    def test_save_load_roundtrip_processing(self):
        """Values written by save_config() are read back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.processing.road_length_threshold = 123.4
            mgr.config.processing.crs_epsg = 25833
            mgr.config.processing.debug_mode = True
            mgr.save_config()

            mgr2 = _make_manager(tmpdir)
            assert mgr2.config.processing.road_length_threshold == 123.4
            assert mgr2.config.processing.crs_epsg == 25833
            assert mgr2.config.processing.debug_mode is True

    @pytest.mark.unit
    def test_save_load_roundtrip_input_paths(self):
        """Input paths survive a save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/my/buildings.shp"
            mgr.config.input_data.filter_file_path = "/my/filter.txt"
            mgr.save_config()

            mgr2 = _make_manager(tmpdir)
            assert mgr2.config.input_data.building_footprints_path == "/my/buildings.shp"
            assert mgr2.config.input_data.filter_file_path == "/my/filter.txt"

    @pytest.mark.unit
    def test_save_load_roundtrip_output_section(self):
        """Output section values survive a save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.output_prefix = "custom_prefix"
            mgr.config.output.overwrite_existing = True
            mgr.save_config()

            mgr2 = _make_manager(tmpdir)
            assert mgr2.config.output.output_prefix == "custom_prefix"
            assert mgr2.config.output.overwrite_existing is True

    @pytest.mark.unit
    def test_config_exists_true_after_save(self):
        """config_exists() returns True after save_config() has been called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            assert mgr.config_exists() is False
            mgr.save_config()
            assert mgr.config_exists() is True


# ---------------------------------------------------------------------------
# TestConfigManagerCreateExampleConfig
# ---------------------------------------------------------------------------

class TestConfigManagerCreateExampleConfig:
    """Tests for ConfigManager.create_example_config()."""

    @pytest.mark.unit
    def test_creates_config_ini_file(self):
        """create_example_config() writes CONFIG.ini to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.create_example_config()
            assert os.path.exists(os.path.join(tmpdir, "CONFIG.ini"))

    @pytest.mark.unit
    def test_example_config_is_loadable_without_error(self):
        """The generated example file can be loaded via load_config()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.create_example_config()
            # Should not raise
            mgr.load_config()

    @pytest.mark.unit
    def test_example_config_contains_processing_section(self):
        """Example file has a [PROCESSING] section with readable values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.create_example_config()
            mgr.load_config()
            assert mgr.config.processing.road_length_threshold == 50.0
            assert mgr.config.processing.output_format == "gpkg"


# ---------------------------------------------------------------------------
# TestConfigManagerUpdateConfig
# ---------------------------------------------------------------------------

class TestConfigManagerUpdateConfig:
    """Tests for ConfigManager.update_config()."""

    @pytest.mark.unit
    def test_update_known_field_changes_value(self):
        """update_config with a valid section/key updates the stored value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.update_config(processing={"max_distance": 999.0})
            assert mgr.config.processing.max_distance == 999.0

    @pytest.mark.unit
    def test_update_multiple_fields_at_once(self):
        """Multiple fields in one section can be updated in a single call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.update_config(processing={"grid_size": 50.0, "crs_epsg": 4326})
            assert mgr.config.processing.grid_size == 50.0
            assert mgr.config.processing.crs_epsg == 4326

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_update_unknown_section_is_silently_ignored(self):
        """Passing an unknown section name does not raise and does not change config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.update_config(nonexistent_section={"foo": "bar"})
            # No exception, config unchanged
            assert mgr.config.processing.max_distance == 200.0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_update_unknown_field_in_known_section_is_ignored(self):
        """Unknown field key inside a valid section is silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.update_config(processing={"nonexistent_key": 42})
            # No exception


# ---------------------------------------------------------------------------
# TestConfigManagerValidatePaths
# ---------------------------------------------------------------------------

class TestConfigManagerValidatePaths:
    """Tests for ConfigManager.validate_paths()."""

    @pytest.mark.unit
    def test_unconfigured_paths_return_none(self):
        """Paths that are empty strings return None (not configured)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            # Default config has no input paths set
            status = mgr.validate_paths()
            assert status["building_footprints"] is None
            assert status["road_network"] is None

    @pytest.mark.unit
    def test_existing_file_returns_true(self):
        """A path pointing to a real file returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_file = os.path.join(tmpdir, "dummy.shp")
            open(real_file, "w").close()

            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = real_file
            status = mgr.validate_paths()
            assert status["building_footprints"] is True

    @pytest.mark.unit
    def test_missing_file_returns_false(self):
        """A path pointing to a non-existent file returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/nonexistent/buildings.shp"
            status = mgr.validate_paths()
            assert status["building_footprints"] is False

    @pytest.mark.unit
    def test_existing_workspace_returns_true(self):
        """workspace_directory pointing to a real directory returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.workspace_directory = tmpdir
            status = mgr.validate_paths()
            assert status["workspace_directory"] is True


# ---------------------------------------------------------------------------
# TestConfigManagerGetMissingPaths
# ---------------------------------------------------------------------------

class TestConfigManagerGetMissingPaths:
    """Tests for ConfigManager.get_missing_paths()."""

    @pytest.mark.unit
    def test_no_configured_input_paths_not_reported_missing(self):
        """Input paths that are empty strings are not reported as missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            # Default: all input data paths are "" → validate_paths returns None → not missing
            missing = mgr.get_missing_paths()
            assert "building_footprints" not in missing
            assert "road_network" not in missing
            assert "partitions" not in missing
            assert "aux_layer" not in missing
            assert "filter_file" not in missing

    @pytest.mark.unit
    def test_nonexistent_configured_path_appears_in_missing(self):
        """A configured but missing path is returned in get_missing_paths()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/no/such/file.shp"
            missing = mgr.get_missing_paths()
            assert "building_footprints" in missing

    @pytest.mark.unit
    def test_existing_configured_path_not_in_missing(self):
        """A configured path that exists is NOT reported as missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_file = os.path.join(tmpdir, "buildings.shp")
            open(real_file, "w").close()

            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = real_file
            missing = mgr.get_missing_paths()
            assert "building_footprints" not in missing


# ---------------------------------------------------------------------------
# TestConfigManagerApplyToUiElements
# ---------------------------------------------------------------------------

class TestConfigManagerApplyToUiElements:
    """Tests for ConfigManager.apply_to_ui_elements()."""

    class _Widget:
        """Minimal widget stub with setText/text."""
        def __init__(self):
            self._text = ""
        def setText(self, text):
            self._text = text
        def text(self):
            return self._text

    @pytest.mark.unit
    def test_sets_hu_path_widget(self):
        """HuPath widget receives the building_footprints_path value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/data/buildings.shp"
            widget = self._Widget()
            mgr.apply_to_ui_elements({"HuPath": widget})
            assert widget.text() == "/data/buildings.shp"

    @pytest.mark.unit
    def test_empty_path_does_not_update_widget(self):
        """An empty path value leaves the widget text unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            # building_footprints_path is "" by default
            widget = self._Widget()
            widget.setText("original")
            mgr.apply_to_ui_elements({"HuPath": widget})
            assert widget.text() == "original"

    @pytest.mark.unit
    def test_missing_ui_key_does_not_raise(self):
        """Calling apply_to_ui_elements with an incomplete dict does not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/data/buildings.shp"
            # HuPath missing from dict — must not raise
            mgr.apply_to_ui_elements({})

    @pytest.mark.unit
    def test_sets_workspace_path_widget(self):
        """WorkspacePath widget receives the workspace_directory value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.workspace_directory = "/workspace"
            widget = self._Widget()
            mgr.apply_to_ui_elements({"WorkspacePath": widget})
            assert widget.text() == "/workspace"

    @pytest.mark.unit
    def test_sets_all_input_path_widgets(self):
        """All five input path widgets are set correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/hu.shp"
            mgr.config.input_data.road_network_path = "/rn.shp"
            mgr.config.input_data.partitions_path = "/part.shp"
            mgr.config.input_data.aux_layer_path = "/aux.shp"
            mgr.config.input_data.filter_file_path = "/filter.txt"

            widgets = {k: self._Widget() for k in ("HuPath", "RnPath", "PartPath", "AuxPath", "FilterPath")}
            mgr.apply_to_ui_elements(widgets)

            assert widgets["HuPath"].text() == "/hu.shp"
            assert widgets["RnPath"].text() == "/rn.shp"
            assert widgets["PartPath"].text() == "/part.shp"
            assert widgets["AuxPath"].text() == "/aux.shp"
            assert widgets["FilterPath"].text() == "/filter.txt"

    @pytest.mark.unit
    def test_widget_without_set_text_does_not_crash(self):
        """A widget without setText must be silently skipped — no AttributeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_path = "/data/buildings.shp"
            # Widget stub that intentionally has no setText
            class NoSetText:
                pass
            # Must not raise
            mgr.apply_to_ui_elements({"HuPath": NoSetText()})

    @pytest.mark.unit
    def test_sets_output_path_widget(self):
        """OutputPath widget receives the output_directory value when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.output_directory = "/specific_output"
            widget = self._Widget()
            mgr.apply_to_ui_elements({"OutputPath": widget})
            assert widget.text() == "/specific_output"

    @pytest.mark.unit
    def test_sets_log_dir_path_widget(self):
        """LogDirPath widget receives the log_directory value when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.ui.log_directory = "/my/logs"
            widget = self._Widget()
            mgr.apply_to_ui_elements({"LogDirPath": widget})
            assert widget.text() == "/my/logs"

    @pytest.mark.unit
    def test_empty_output_directory_does_not_update_output_path_widget(self):
        """OutputPath widget is not updated when output_directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.output_directory = ""
            widget = self._Widget()
            widget.setText("unchanged")
            mgr.apply_to_ui_elements({"OutputPath": widget})
            assert widget.text() == "unchanged"


# ---------------------------------------------------------------------------
# TestGetEffectiveDirectories
# ---------------------------------------------------------------------------

class TestGetEffectiveDirectories:
    """Tests for get_effective_output_directory and get_effective_log_directory."""

    @pytest.mark.unit
    def test_effective_output_uses_output_directory_when_set(self):
        """output_directory takes precedence over workspace_directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.workspace_directory = "/workspace"
            mgr.config.output.output_directory = "/specific_output"
            assert mgr.get_effective_output_directory() == "/specific_output"

    @pytest.mark.unit
    def test_effective_output_falls_back_to_workspace(self):
        """When output_directory is empty, workspace_directory is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.output.workspace_directory = "/workspace"
            mgr.config.output.output_directory = ""
            assert mgr.get_effective_output_directory() == "/workspace"

    @pytest.mark.unit
    def test_effective_log_uses_configured_directory(self):
        """When ui.log_directory is set, it is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.ui.log_directory = "/my/logs"
            assert mgr.get_effective_log_directory() == "/my/logs"

    @pytest.mark.unit
    def test_effective_log_falls_back_to_plugin_root_logs(self):
        """When ui.log_directory is empty, <plugin_root>/logs is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.ui.log_directory = ""
            assert mgr.get_effective_log_directory() == os.path.join(tmpdir, "logs")


# ---------------------------------------------------------------------------
# TestGetProcessingParameters
# ---------------------------------------------------------------------------

class TestGetProcessingParameters:
    """Tests for ConfigManager.get_processing_parameters()."""

    @pytest.mark.unit
    def test_returns_dict(self):
        """get_processing_parameters() returns a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            params = mgr.get_processing_parameters()
            assert isinstance(params, dict)

    @pytest.mark.unit
    def test_contains_all_expected_keys(self):
        """All documented parameter keys are present in the result dict."""
        expected_keys = {
            "road_length_threshold", "coordinate_tolerance", "buffer_distance",
            "grid_size", "min_building_count", "density_threshold",
            "min_cluster_size", "max_distance", "part_start", "part_end",
            "part_list", "crs_epsg", "output_format",
            "min_overlap_blocks", "global_footprint_density", "min_area",
            "min_patch_size", "max_hole_size", "max_gap_size",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            params = mgr.get_processing_parameters()
            assert expected_keys.issubset(params.keys())

    @pytest.mark.unit
    def test_values_match_current_config(self):
        """Values in the dict reflect the current config state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.processing.max_distance = 555.0
            mgr.config.processing.crs_epsg = 25833
            params = mgr.get_processing_parameters()
            assert params["max_distance"] == 555.0
            assert params["crs_epsg"] == 25833

    @pytest.mark.unit
    def test_default_values_match_processing_config_defaults(self):
        """Default dict values match ProcessingConfig defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            params = mgr.get_processing_parameters()
            assert params["road_length_threshold"] == 50.0
            assert params["crs_epsg"] == 25832
            assert params["output_format"] == "gpkg"


# ---------------------------------------------------------------------------
# TestValidationCacheConfig — new dataclass
# ---------------------------------------------------------------------------

class TestValidationCacheConfig:
    """Tests for the ValidationCacheConfig dataclass."""

    @pytest.mark.unit
    def test_default_errors_is_empty_json_list(self):
        """Default errors field is '[]' — a JSON-encoded empty list."""
        cfg = ValidationCacheConfig()
        assert cfg.errors == "[]"

    @pytest.mark.unit
    def test_default_warnings_is_empty_json_list(self):
        """Default warnings field is '[]' — a JSON-encoded empty list."""
        cfg = ValidationCacheConfig()
        assert cfg.warnings == "[]"


# ---------------------------------------------------------------------------
# TestInputDataChecksumFields — new fields on InputDataConfig
# ---------------------------------------------------------------------------

class TestInputDataChecksumFields:
    """Tests for the five checksum fields added to InputDataConfig."""

    @pytest.mark.unit
    def test_all_checksum_fields_default_to_empty_string(self):
        """All five checksum fields default to ''."""
        cfg = InputDataConfig()
        assert cfg.building_footprints_checksum == ""
        assert cfg.road_network_checksum == ""
        assert cfg.partitions_checksum == ""
        assert cfg.aux_layer_checksum == ""
        assert cfg.filter_file_checksum == ""

    @pytest.mark.unit
    def test_checksum_fields_accept_and_store_string_values(self):
        """Checksum fields store arbitrary string values without error."""
        cfg = InputDataConfig()
        cfg.building_footprints_checksum = "aabbccddeeff0011"
        assert cfg.building_footprints_checksum == "aabbccddeeff0011"


# ---------------------------------------------------------------------------
# TestPluginConfigValidationCache — new field on PluginConfig
# ---------------------------------------------------------------------------

class TestPluginConfigValidationCache:
    """Tests for the validation_cache field added to PluginConfig."""

    @pytest.mark.unit
    def test_plugin_config_has_validation_cache_attribute(self):
        """PluginConfig exposes a validation_cache attribute of type ValidationCacheConfig."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            cfg = mgr.get_config()
            assert hasattr(cfg, "validation_cache")
            assert isinstance(cfg.validation_cache, ValidationCacheConfig)

    @pytest.mark.unit
    def test_validation_cache_defaults_to_empty_json_lists(self):
        """Fresh PluginConfig has validation_cache with errors='[]' and warnings='[]'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            cfg = mgr.get_config()
            assert cfg.validation_cache.errors == "[]"
            assert cfg.validation_cache.warnings == "[]"


# ---------------------------------------------------------------------------
# TestConfigManagerChecksumRoundtrip — save/load for new fields
# ---------------------------------------------------------------------------

class TestConfigManagerChecksumRoundtrip:
    """Tests for checksum and validation-cache persistence in save_config / load_config."""

    @pytest.mark.unit
    def test_all_five_checksums_survive_save_load_cycle(self):
        """All five checksum fields are written and read back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.input_data.building_footprints_checksum = "aabb11"
            mgr.config.input_data.road_network_checksum = "ccdd22"
            mgr.config.input_data.partitions_checksum = "eeff33"
            mgr.config.input_data.aux_layer_checksum = "aabb44"
            mgr.config.input_data.filter_file_checksum = "ccdd55"
            mgr.save_config()

            mgr2 = _make_manager(tmpdir)
            assert mgr2.config.input_data.building_footprints_checksum == "aabb11"
            assert mgr2.config.input_data.road_network_checksum == "ccdd22"
            assert mgr2.config.input_data.partitions_checksum == "eeff33"
            assert mgr2.config.input_data.aux_layer_checksum == "aabb44"
            assert mgr2.config.input_data.filter_file_checksum == "ccdd55"

    @pytest.mark.unit
    def test_save_writes_validation_cache_section(self):
        """save_config creates a [VALIDATION_CACHE] section in CONFIG.ini."""
        import configparser
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.validation_cache.errors = '["path error"]'
            mgr.config.validation_cache.warnings = '["minor warning"]'
            mgr.save_config()

            parser = configparser.ConfigParser()
            parser.read(os.path.join(tmpdir, "CONFIG.ini"), encoding="utf-8")
            assert parser.has_section("VALIDATION_CACHE"), \
                "[VALIDATION_CACHE] section must exist in CONFIG.ini"

    @pytest.mark.unit
    def test_save_writes_correct_errors_and_warnings_values(self):
        """save_config writes the exact errors and warnings strings to [VALIDATION_CACHE]."""
        import configparser
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.validation_cache.errors = '["err_a", "err_b"]'
            mgr.config.validation_cache.warnings = '["warn_x"]'
            mgr.save_config()

            parser = configparser.ConfigParser()
            parser.read(os.path.join(tmpdir, "CONFIG.ini"), encoding="utf-8")
            assert parser["VALIDATION_CACHE"]["errors"] == '["err_a", "err_b"]'
            assert parser["VALIDATION_CACHE"]["warnings"] == '["warn_x"]'

    @pytest.mark.unit
    def test_validation_cache_survives_save_load_cycle(self):
        """Validation cache errors and warnings round-trip through save and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.config.validation_cache.errors = '["path error"]'
            mgr.config.validation_cache.warnings = '["minor warning"]'
            mgr.save_config()

            mgr2 = _make_manager(tmpdir)
            assert mgr2.config.validation_cache.errors == '["path error"]'
            assert mgr2.config.validation_cache.warnings == '["minor warning"]'

    @pytest.mark.unit
    def test_load_reads_checksum_keys_from_input_data_section(self):
        """load_config reads checksum keys from an existing [INPUT_DATA] section."""
        content = (
            "[INPUT_DATA]\n"
            "building_footprints_path = /data/buildings.shp\n"
            "building_footprints_checksum = abc123def456\n"
            "road_network_checksum = 11223344\n"
            "filter_file_checksum = ff998877\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.input_data.building_footprints_checksum == "abc123def456"
            assert mgr.config.input_data.road_network_checksum == "11223344"
            assert mgr.config.input_data.filter_file_checksum == "ff998877"

    @pytest.mark.unit
    def test_load_reads_validation_cache_errors_and_warnings(self):
        """load_config reads errors and warnings from [VALIDATION_CACHE]."""
        content = (
            "[VALIDATION_CACHE]\n"
            'errors = ["err1", "err2"]\n'
            'warnings = ["warn1"]\n'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.validation_cache.errors == '["err1", "err2"]'
            assert mgr.config.validation_cache.warnings == '["warn1"]'

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_missing_checksum_keys_in_input_data_default_to_empty_string(self):
        """[INPUT_DATA] without checksum keys leaves all checksum fields as ''."""
        content = (
            "[INPUT_DATA]\n"
            "building_footprints_path = /data/buildings.shp\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.input_data.building_footprints_checksum == ""
            assert mgr.config.input_data.road_network_checksum == ""
            assert mgr.config.input_data.partitions_checksum == ""
            assert mgr.config.input_data.aux_layer_checksum == ""
            assert mgr.config.input_data.filter_file_checksum == ""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_missing_validation_cache_section_keeps_default_empty_lists(self):
        """Config without [VALIDATION_CACHE] leaves errors and warnings as '[]'."""
        content = "[PROCESSING]\nroad_length_threshold = 50.0\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_ini(tmpdir, content)
            mgr = _make_manager(tmpdir)
            assert mgr.config.validation_cache.errors == "[]"
            assert mgr.config.validation_cache.warnings == "[]"
