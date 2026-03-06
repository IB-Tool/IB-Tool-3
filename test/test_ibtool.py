"""
Tests for ibtool/ibtool/ibtool.py.

The module exposes two components under test:

  ProcessingThread(QThread)
    - Background thread with progress_update and log_message signals.

  IBTool(iface)
    - Main plugin class; constructor requires a QGIS iface stub and calls
      QSettings to detect the locale.

Unit tests cover (no Processing or real iface operations):
  - ProcessingThread: instantiation does not crash
  - ProcessingThread: isRunning() is False directly after construction
  - ProcessingThread: progress_update signal exists
  - ProcessingThread: log_message signal exists
  - IBTool.tr: returns a non-empty string for any string input
  - IBTool._collect_params: returns a dict containing all 11 expected keys
  - IBTool.update_progress: sets dlg.ProgressBar to the given value
  - IBTool.update_messages: appends text to dlg.MessageBox
  - IBTool.cancel_processing: does not crash when the thread is idle
  - IBTool.load_filter_file: does not crash when file path does not exist
  - IBTool.load_filter_file: populates txtPositive / txtNegative from a valid file
  - IBTool.load_filter_file: empty file / comments-only edge cases
  - IBTool._apply_config_to_ui: early-return when no config exists
  - IBTool._apply_config_to_ui: early-return when auto_load_last_used=False
  - IBTool._apply_config_to_ui: calls apply_to_ui_elements when config is enabled
  - IBTool._save_config_from_ui: calls config_manager.update_config and save_config
  - IBTool.setup_logging_in_plugin: populates LogLevelBox with valid levels
  - IBTool.add_action: returns QAction, updates self.actions, respects flags
  - IBTool.initGui: sets first_start=True, registers one action
  - IBTool.unload: delegates remove calls to iface, closes logger
  - IBTool.run_validation: enables/disables StartButton, clears MessageBox
  - IBTool._display_validation_result: correct log messages for all result branches
  - IBTool._update_phase: forwards args to dlg.set_phase_progress; boundary values
  - IBTool._load_input_layers: returns 5-tuple; 4 load calls; spatial indices; merges aux+rn
  - IBTool._run_partition_pipeline: skip <10 buildings; skip MST failure; success;
      boundary 10 buildings; zero buildings edge case
"""
# pylint: disable=too-many-lines,protected-access,import-outside-toplevel,wrong-import-order

import pytest
from unittest.mock import patch, MagicMock

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.ibtool.ibtool import IBTool, ProcessingThread  # noqa: E402


# ---------------------------------------------------------------------------
# Helper — create IBTool with QSettings mocked to avoid locale issues
# ---------------------------------------------------------------------------

def _make_tool() -> IBTool:
    """Instantiate IBTool with QSettings patched to return a safe locale."""
    with patch("ibtool.ibtool.ibtool.QSettings") as mock_qs:
        mock_qs.return_value.value.return_value = "de_DE"
        return IBTool(_IFACE)


# ---------------------------------------------------------------------------
# TestProcessingThread
# ---------------------------------------------------------------------------

class TestProcessingThread:
    """Unit tests for the ProcessingThread QThread subclass."""

    @pytest.mark.unit
    def test_can_be_instantiated(self):
        """ProcessingThread() must construct without raising."""
        thread = ProcessingThread()

        assert thread is not None

    @pytest.mark.unit
    def test_not_running_after_init(self):
        """isRunning() must be False directly after construction."""
        thread = ProcessingThread()

        assert not thread.isRunning(), \
            "Thread must not be running immediately after instantiation"

    @pytest.mark.unit
    def test_has_progress_update_signal(self):
        """ProcessingThread must expose a progress_update signal."""
        thread = ProcessingThread()

        assert hasattr(thread, "progress_update"), \
            "ProcessingThread must have a progress_update signal"

    @pytest.mark.unit
    def test_has_log_message_signal(self):
        """ProcessingThread must expose a log_message signal."""
        thread = ProcessingThread()

        assert hasattr(thread, "log_message"), \
            "ProcessingThread must have a log_message signal"

    @pytest.mark.unit
    def test_signal_can_be_connected(self):
        """progress_update and log_message signals must accept slot connections."""
        thread = ProcessingThread()
        received = []

        thread.progress_update.connect(lambda v: received.append(("progress", v)))
        thread.log_message.connect(lambda m: received.append(("msg", m)))

        # Emit manually — does not require the thread to actually run
        thread.progress_update.emit(50)
        thread.log_message.emit("hello")

        assert ("progress", 50) in received
        assert ("msg", "hello") in received


# ---------------------------------------------------------------------------
# TestIBTool
# ---------------------------------------------------------------------------

class TestIBTool:  # pylint: disable=too-many-public-methods
    """Unit tests for the IBTool plugin class."""

    @classmethod
    def setup_class(cls):
        """Create a single IBTool instance for all tests in the class."""
        cls.tool = _make_tool()

    # --- tr ---

    @pytest.mark.unit
    def test_tr_returns_string(self):
        """tr() must return a string for any string input."""
        result = self.tool.tr("Test message")

        assert isinstance(result, str), \
            f"tr() must return str, got {type(result)}"

    @pytest.mark.unit
    def test_tr_non_empty_input_non_empty_output(self):
        """tr() must return a non-empty string for non-empty input."""
        result = self.tool.tr("Hello")

        assert len(result) > 0, "tr('Hello') must not return an empty string"

    # --- _collect_params ---

    @pytest.mark.unit
    def test_collect_params_returns_dict(self):
        """_collect_params must return a dict."""
        result = self.tool._collect_params()

        assert isinstance(result, dict), \
            f"_collect_params must return dict, got {type(result)}"

    @pytest.mark.unit
    def test_collect_params_has_all_expected_keys(self):
        """_collect_params must contain exactly the 11 expected parameter keys."""
        expected_keys = {
            "min_overlap_blocks",
            "global_footprint_density",
            "min_area",
            "min_bdg_count",
            "min_patch_size",
            "max_hole_size",
            "max_gap_size",
            "spatial_reference_text",
            "part_start",
            "part_end",
            "part_list",
        }

        result = self.tool._collect_params()

        missing = expected_keys - set(result.keys())
        assert not missing, f"_collect_params missing keys: {missing}"

    # --- update_progress ---

    @pytest.mark.unit
    def test_update_progress_sets_progress_bar_value(self):
        """update_progress(n) must set dlg.ProgressBar to n."""
        self.tool.update_progress(73)

        assert self.tool.dlg.ProgressBar.value() == 73, \
            f"Expected ProgressBar value 73, got {self.tool.dlg.ProgressBar.value()}"

    @pytest.mark.unit
    def test_update_progress_zero(self):
        """update_progress(0) must reset the progress bar to 0."""
        self.tool.update_progress(0)

        assert self.tool.dlg.ProgressBar.value() == 0

    # --- update_messages ---

    @pytest.mark.unit
    def test_update_messages_appends_text_to_message_box(self):
        """update_messages must append the given text to dlg.MessageBox."""
        self.tool.dlg.MessageBox.clear()
        self.tool.update_messages("unit test message")

        content = self.tool.dlg.MessageBox.toPlainText()
        assert "unit test message" in content, \
            f"Expected 'unit test message' in MessageBox, got: {content!r}"

    @pytest.mark.unit
    def test_update_messages_multiple_calls_accumulate(self):
        """Multiple update_messages calls must accumulate in the MessageBox."""
        self.tool.dlg.MessageBox.clear()
        self.tool.update_messages("line one")
        self.tool.update_messages("line two")

        content = self.tool.dlg.MessageBox.toPlainText()
        assert "line one" in content
        assert "line two" in content

    # --- cancel_processing ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_cancel_processing_when_idle_does_not_crash(self):
        """cancel_processing must not raise when the processing thread is idle."""
        assert not self.tool.thread.isRunning(), \
            "Precondition: thread must not be running at test start"

        self.tool.cancel_processing()  # Must not raise

    # --- load_filter_file ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_filter_file_missing_path_does_not_crash(self):
        """load_filter_file must not raise for a non-existent file path."""
        self.tool.load_filter_file("/nonexistent/path/to/filter.txt")
        # No exception expected; text fields are unchanged

    @pytest.mark.unit
    def test_load_filter_file_populates_positive_section(self, tmp_path):
        """load_filter_file must populate txtPositive from #Filter positive section."""
        filter_file = tmp_path / "filter.txt"
        filter_file.write_text(
            "#Filter positive\n1010\n1020\n#Filter negative\n9999\n",
            encoding="utf-8",
        )

        self.tool.load_filter_file(str(filter_file))

        positive = self.tool.dlg.txtPositive.toPlainText()
        assert "1010" in positive, \
            f"Expected '1010' in txtPositive, got: {positive!r}"
        assert "1020" in positive, \
            f"Expected '1020' in txtPositive, got: {positive!r}"

    @pytest.mark.unit
    def test_load_filter_file_populates_negative_section(self, tmp_path):
        """load_filter_file must populate txtNegative from #Filter negative section."""
        filter_file = tmp_path / "filter.txt"
        filter_file.write_text(
            "#Filter positive\n1010\n#Filter negative\n9999\n8888\n",
            encoding="utf-8",
        )

        self.tool.load_filter_file(str(filter_file))

        negative = self.tool.dlg.txtNegative.toPlainText()
        assert "9999" in negative, \
            f"Expected '9999' in txtNegative, got: {negative!r}"
        assert "8888" in negative, \
            f"Expected '8888' in txtNegative, got: {negative!r}"

    @pytest.mark.unit
    def test_load_filter_file_comment_lines_not_included(self, tmp_path):
        """load_filter_file must skip lines starting with '#'."""
        filter_file = tmp_path / "filter.txt"
        filter_file.write_text(
            "# This is a comment\n#Filter positive\n1010\n",
            encoding="utf-8",
        )

        self.tool.load_filter_file(str(filter_file))

        positive = self.tool.dlg.txtPositive.toPlainText()
        assert "comment" not in positive.lower(), \
            "Comment lines must not appear in txtPositive"

    # --- _apply_config_to_ui ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_apply_config_to_ui_no_config_returns_early_without_crash(self):
        """_apply_config_to_ui must not crash when config_exists() returns False."""
        with patch.object(self.tool.config_manager, "config_exists",
                          return_value=False):
            self.tool._apply_config_to_ui()  # Must not raise

    # --- _save_config_from_ui ---

    @pytest.mark.unit
    def test_save_config_from_ui_calls_update_and_save(self):
        """_save_config_from_ui must call config_manager.update_config and save_config."""
        with patch.object(self.tool.config_manager, "update_config") as mock_update, \
             patch.object(self.tool.config_manager, "save_config") as mock_save:
            self.tool._save_config_from_ui()

        mock_update.assert_called_once()
        mock_save.assert_called_once()

    @pytest.mark.unit
    def test_save_config_from_ui_does_not_crash(self):
        """_save_config_from_ui must not raise with default (empty) widget values."""
        with patch.object(self.tool.config_manager, "update_config"), \
             patch.object(self.tool.config_manager, "save_config"):
            self.tool._save_config_from_ui()  # Must not raise

    # --- run() orchestration (STEP 10 — test-plan.md) ---

    @pytest.mark.unit
    def test_run_with_mock_iface_does_not_raise(self):
        """run() must not raise when version_check and _apply_config_to_ui are patched."""
        tool = _make_tool()
        tool.first_start = True  # trigger the first-start dialog initialisation branch

        with patch("ibtool.ibtool.ibtool.version_check"), \
             patch.object(tool, "_apply_config_to_ui"):
            tool.run()  # must complete without raising

    @pytest.mark.unit
    def test_run_shows_dialog(self):
        """run() calls show() on the dialog to display it to the user."""
        tool = _make_tool()
        tool.first_start = False  # skip first-start branch so dlg is not replaced

        with patch("ibtool.ibtool.ibtool.version_check"), \
             patch.object(tool, "_apply_config_to_ui"), \
             patch.object(tool.dlg, "show") as mock_show:
            tool.run()

        mock_show.assert_called_once()

    @pytest.mark.unit
    def test_run_on_second_call_does_not_replace_dialog(self):
        """Second run() call must reuse the existing dialog instance, not replace it."""
        tool = _make_tool()
        tool.first_start = False  # simulate state after the first run
        original_dlg = tool.dlg

        with patch("ibtool.ibtool.ibtool.version_check"), \
             patch.object(tool, "_apply_config_to_ui"), \
             patch.object(tool.dlg, "show"):
            tool.run()

        assert tool.dlg is original_dlg, \
            "Second run() call must not replace tool.dlg with a new IBToolDialog instance"

    # --- _apply_config_to_ui (additional branches) ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_apply_config_to_ui_auto_load_false_returns_early(self):
        """_apply_config_to_ui must return early when auto_load_last_used is False."""
        tool = _make_tool()
        mock_cfg = MagicMock()
        mock_cfg.ui.auto_load_last_used = False

        with patch.object(tool.config_manager, "config_exists", return_value=True), \
             patch.object(tool.config_manager, "get_config", return_value=mock_cfg), \
             patch.object(tool.config_manager, "apply_to_ui_elements") as mock_apply:
            tool._apply_config_to_ui()

        mock_apply.assert_not_called()

    @pytest.mark.unit
    def test_apply_config_to_ui_calls_apply_to_ui_elements_when_enabled(self):
        """_apply_config_to_ui must call apply_to_ui_elements when auto_load_last_used=True."""
        tool = _make_tool()
        mock_cfg = MagicMock()
        mock_cfg.ui.auto_load_last_used = True
        mock_cfg.ui.log_level = "INFO"
        mock_cfg.processing.crs_epsg = 0
        mock_cfg.processing.part_start = 0
        mock_cfg.processing.part_end = 0
        mock_cfg.processing.part_list = ""
        mock_cfg.processing.min_building_count = 0
        mock_cfg.processing.min_overlap_blocks = 0
        mock_cfg.processing.global_footprint_density = 0
        mock_cfg.processing.min_area = 0
        mock_cfg.processing.min_patch_size = 0
        mock_cfg.processing.max_hole_size = 0
        mock_cfg.processing.max_gap_size = 0
        mock_cfg.processing.debug_mode = False
        mock_cfg.processing.delete_part_log = False
        mock_cfg.input_data.filter_file_path = ""

        with patch.object(tool.config_manager, "config_exists", return_value=True), \
             patch.object(tool.config_manager, "get_config", return_value=mock_cfg), \
             patch.object(tool.config_manager, "apply_to_ui_elements") as mock_apply, \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._apply_config_to_ui()

        mock_apply.assert_called_once()

    # --- load_filter_file (additional edge cases) ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_filter_file_empty_file_does_not_crash(self, tmp_path):
        """load_filter_file must not crash when the file exists but is empty."""
        tool = _make_tool()
        filter_file = tmp_path / "empty.txt"
        filter_file.write_text("", encoding="utf-8")

        tool.load_filter_file(str(filter_file))  # Must not raise

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_filter_file_only_comments_yields_empty_sections(self, tmp_path):
        """load_filter_file must leave both widget sections empty for a comments-only file."""
        tool = _make_tool()  # Fresh instance to avoid widget state pollution
        filter_file = tmp_path / "comments_only.txt"
        filter_file.write_text(
            "# This is a header comment\n# Another comment\n\n",
            encoding="utf-8",
        )

        tool.load_filter_file(str(filter_file))

        assert tool.dlg.txtPositive.toPlainText() == "", \
            "txtPositive must be empty when filter file contains only comments"
        assert tool.dlg.txtNegative.toPlainText() == "", \
            "txtNegative must be empty when filter file contains only comments"


# ---------------------------------------------------------------------------
# TestSetupLoggingInPlugin
# ---------------------------------------------------------------------------

class TestSetupLoggingInPlugin:
    """Unit tests for IBTool.setup_logging_in_plugin."""

    @pytest.mark.unit
    def test_valid_levels_are_added_to_combo_box(self):
        """setup_logging_in_plugin must add INFO/WARNING/CRITICAL/SUCCESS to LogLevelBox."""
        tool = _make_tool()
        with patch("ibtool.ibtool.ibtool.logger"):
            tool.setup_logging_in_plugin()

        items = [tool.dlg.LogLevelBox.itemText(i)
                 for i in range(tool.dlg.LogLevelBox.count())]
        for level in ("INFO", "WARNING", "CRITICAL", "SUCCESS"):
            assert level in items, f"Expected '{level}' in LogLevelBox items"

    @pytest.mark.unit
    def test_default_level_is_info(self):
        """setup_logging_in_plugin must select 'INFO' as the default log level."""
        tool = _make_tool()
        with patch("ibtool.ibtool.ibtool.logger"):
            tool.setup_logging_in_plugin()

        assert tool.dlg.LogLevelBox.currentText() == "INFO", \
            "Default log level must be INFO"

    @pytest.mark.unit
    def test_can_be_called_without_crash(self):
        """setup_logging_in_plugin must not raise in a freshly constructed plugin instance."""
        tool = _make_tool()
        with patch("ibtool.ibtool.ibtool.logger"):
            tool.setup_logging_in_plugin()  # Must not raise


# ---------------------------------------------------------------------------
# TestAddAction
# ---------------------------------------------------------------------------

class TestAddAction:
    """Unit tests for IBTool.add_action."""

    @staticmethod
    def _add(tool, **kwargs):
        """Call add_action with a MagicMock iface (avoids real Qt toolbar/menu calls)."""
        tool.iface = MagicMock()
        defaults = {
            "icon_path": "",
            "text": "Test Action",
            "callback": lambda: None,
            "parent": _PARENT,
        }
        defaults.update(kwargs)
        return tool.add_action(**defaults)

    @pytest.mark.unit
    def test_returns_qaction(self):
        """add_action must return a QAction instance."""
        from qgis.PyQt.QtWidgets import QAction
        tool = _make_tool()
        action = self._add(tool)
        assert isinstance(action, QAction)

    @pytest.mark.unit
    def test_appends_to_actions_list(self):
        """add_action must append the created action to self.actions."""
        tool = _make_tool()
        initial_count = len(tool.actions)
        self._add(tool)
        assert len(tool.actions) == initial_count + 1

    @pytest.mark.unit
    def test_action_disabled_when_enabled_flag_false(self):
        """add_action must create a disabled action when enabled_flag=False."""
        tool = _make_tool()
        action = self._add(tool, enabled_flag=False)
        assert not action.isEnabled(), \
            "Action must be disabled when enabled_flag=False"

    @pytest.mark.unit
    def test_not_added_to_toolbar_when_flag_false(self):
        """add_action must not call iface.addToolBarIcon when add_to_toolbar=False."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.add_action(
            icon_path="",
            text="Test",
            callback=lambda: None,
            parent=_PARENT,
            add_to_toolbar=False,
        )
        tool.iface.addToolBarIcon.assert_not_called()

    @pytest.mark.unit
    def test_not_added_to_menu_when_flag_false(self):
        """add_action must not call iface.addPluginToMenu when add_to_menu=False."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.add_action(
            icon_path="",
            text="Test",
            callback=lambda: None,
            parent=_PARENT,
            add_to_menu=False,
        )
        tool.iface.addPluginToMenu.assert_not_called()

    @pytest.mark.unit
    def test_sets_status_tip_when_provided(self):
        """add_action must set the status tip when status_tip is not None."""
        tool = _make_tool()
        action = self._add(tool, status_tip="My tooltip text")
        assert action.statusTip() == "My tooltip text"


# ---------------------------------------------------------------------------
# TestInitGui
# ---------------------------------------------------------------------------

class TestInitGui:
    """Unit tests for IBTool.initGui."""

    @pytest.mark.unit
    def test_sets_first_start_to_true(self):
        """initGui must set first_start=True after completing."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.iface.mainWindow.return_value = _PARENT  # QAction requires a real QObject
        with patch.object(tool, "setup_logging_in_plugin"):
            tool.initGui()
        assert tool.first_start is True

    @pytest.mark.unit
    def test_registers_exactly_one_action(self):
        """initGui must add exactly one action to self.actions."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.iface.mainWindow.return_value = _PARENT  # QAction requires a real QObject
        initial_count = len(tool.actions)
        with patch.object(tool, "setup_logging_in_plugin"):
            tool.initGui()
        assert len(tool.actions) == initial_count + 1


# ---------------------------------------------------------------------------
# TestUnload
# ---------------------------------------------------------------------------

class TestUnload:
    """Unit tests for IBTool.unload."""

    @pytest.mark.unit
    def test_calls_remove_toolbar_icon_for_each_action(self):
        """unload must call iface.removeToolBarIcon once per registered action."""
        from qgis.PyQt.QtWidgets import QAction
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.actions = [QAction(f"Action {i}") for i in range(3)]

        with patch("ibtool.ibtool.ibtool.logger"):
            tool.unload()

        assert tool.iface.removeToolBarIcon.call_count == 3

    @pytest.mark.unit
    def test_calls_remove_plugin_menu_for_each_action(self):
        """unload must call iface.removePluginMenu once per registered action."""
        from qgis.PyQt.QtWidgets import QAction
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.actions = [QAction(f"Action {i}") for i in range(2)]

        with patch("ibtool.ibtool.ibtool.logger"):
            tool.unload()

        assert tool.iface.removePluginMenu.call_count == 2

    @pytest.mark.unit
    def test_calls_logger_close_logger(self):
        """unload must call logger.close_logger() to release file handles."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.actions = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool.unload()

        mock_logger.close_logger.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_unload_with_no_actions_does_not_crash(self):
        """unload must not crash when self.actions is empty."""
        tool = _make_tool()
        tool.iface = MagicMock()
        tool.actions = []

        with patch("ibtool.ibtool.ibtool.logger"):
            tool.unload()  # Must not raise


# ---------------------------------------------------------------------------
# TestRunValidation
# ---------------------------------------------------------------------------

class TestRunValidation:
    """Unit tests for IBTool.run_validation."""

    @pytest.mark.unit
    def test_valid_result_enables_start_button(self):
        """run_validation must enable StartButton when InputValidator returns is_valid=True."""
        tool = _make_tool()
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.errors = []
        mock_result.warnings = []

        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        assert tool.dlg.StartButton.isEnabled(), \
            "StartButton must be enabled after successful validation"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_invalid_result_disables_start_button(self):
        """run_validation must disable StartButton when InputValidator returns is_valid=False."""
        tool = _make_tool()
        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.errors = ["Missing HU layer path"]
        mock_result.warnings = []

        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        assert not tool.dlg.StartButton.isEnabled(), \
            "StartButton must remain disabled after failed validation"

    @pytest.mark.unit
    def test_message_box_is_cleared_before_validation(self):
        """run_validation must clear the MessageBox before displaying new results."""
        tool = _make_tool()
        tool.dlg.MessageBox.appendPlainText("stale result from previous run")
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.errors = []
        mock_result.warnings = []

        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        content = tool.dlg.MessageBox.toPlainText()
        assert "stale result from previous run" not in content, \
            "MessageBox must be cleared before new validation results are shown"


# ---------------------------------------------------------------------------
# TestDisplayValidationResult
# ---------------------------------------------------------------------------

class TestDisplayValidationResult:
    """Unit tests for IBTool._display_validation_result."""

    @pytest.mark.unit
    def test_valid_no_warnings_logs_erfolgreich(self):
        """_display_validation_result must log VALIDATION SUCCESSFUL for a fully valid result."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("VALIDATION SUCCESSFUL" in m for m in logged_msgs), \
            "Expected 'VALIDATION SUCCESSFUL' in logged messages"

    @pytest.mark.unit
    def test_errors_are_logged_with_validierungsfehler_header(self):
        """_display_validation_result must log VALIDATION ERRORS when errors are present."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = False
        result.errors = ["Error A", "Error B"]
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("VALIDATION ERRORS" in m for m in logged_msgs), \
            "Expected 'VALIDATION ERRORS' in logged messages"

    @pytest.mark.unit
    def test_each_error_is_logged_individually(self):
        """_display_validation_result must log each error as a separate log entry."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = False
        result.errors = ["Error A", "Error B"]
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("Error A" in m for m in logged_msgs)
        assert any("Error B" in m for m in logged_msgs)

    @pytest.mark.unit
    def test_warnings_are_logged_with_warnungen_header(self):
        """_display_validation_result must log WARNINGS section when warnings are present."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = ["Minor warning"]

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("WARNINGS" in m for m in logged_msgs), \
            "Expected 'WARNINGS' in logged messages"

    @pytest.mark.unit
    def test_invalid_result_logs_fehlgeschlagen(self):
        """_display_validation_result must log 'failed' for an invalid result."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = False
        result.errors = ["Bad path"]
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("failed" in m for m in logged_msgs), \
            "Expected 'failed' in logged messages for invalid result"

    @pytest.mark.unit
    def test_valid_with_warnings_logs_bestanden_mit_warnungen(self):
        """_display_validation_result must log 'passed' for valid result with warnings."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = ["Non-critical issue"]

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("passed" in m for m in logged_msgs), \
            "Expected 'passed' in logged messages for valid result with warnings"


# ---------------------------------------------------------------------------
# Shared helpers for new test classes
# ---------------------------------------------------------------------------

_ALL_CHECKSUM_FIELDS = ("HuPath", "RnPath", "PartPath", "AuxPath", "FilterPath")


def _set_matching_checksums(tool, value: str = "deadbeef1234") -> None:  # pragma: allowlist secret
    """Populate both checksum dicts with the same non-empty value for all 5 fields."""
    for field in _ALL_CHECKSUM_FIELDS:
        tool._file_checksums[field] = value
        tool._validated_checksums[field] = value


# ---------------------------------------------------------------------------
# TestCheckPathFieldChecksum
# ---------------------------------------------------------------------------

class TestCheckPathFieldChecksum:
    """Tests for the checksum-computation logic added to _check_path_field."""

    @pytest.mark.unit
    def test_valid_file_stores_md5_checksum(self, tmp_path):
        """_check_path_field stores a 32-char MD5 checksum for an existing file."""
        tool = _make_tool()
        f = tmp_path / "buildings.shp"
        f.write_bytes(b"dummy shapefile content")

        tool._check_path_field("HuPath", str(f))

        assert "HuPath" in tool._file_checksums, \
            "Checksum must be stored for a valid HuPath file"
        assert len(tool._file_checksums["HuPath"]) == 32, \
            "MD5 checksum must be exactly 32 hex characters"

    @pytest.mark.unit
    def test_stored_checksum_matches_direct_md5(self, tmp_path):
        """Stored checksum equals the MD5 of the exact file bytes."""
        import hashlib
        tool = _make_tool()
        content = b"road network binary data"
        f = tmp_path / "roads.shp"
        f.write_bytes(content)

        tool._check_path_field("RnPath", str(f))

        expected = hashlib.md5(content, usedforsecurity=False).hexdigest()  # nosec B324  # pylint: disable=unexpected-keyword-arg
        assert tool._file_checksums.get("RnPath") == expected

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_nonexistent_path_removes_existing_checksum(self):
        """_check_path_field removes a stale checksum when the file no longer exists."""
        tool = _make_tool()
        tool._file_checksums["HuPath"] = "stale_checksum"

        tool._check_path_field("HuPath", "/nonexistent/buildings.shp")

        assert "HuPath" not in tool._file_checksums, \
            "Stale checksum must be removed for a non-existent file"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_path_removes_existing_checksum(self):
        """_check_path_field removes the checksum when path is cleared to ''."""
        tool = _make_tool()
        tool._file_checksums["HuPath"] = "some_checksum"

        tool._check_path_field("HuPath", "")

        assert "HuPath" not in tool._file_checksums, \
            "Checksum must be removed when path is empty"

    @pytest.mark.unit
    def test_non_checksum_field_does_not_store_checksum(self, tmp_path):
        """_check_path_field skips checksum computation for WorkspacePath (directory field)."""
        tool = _make_tool()

        tool._check_path_field("WorkspacePath", str(tmp_path))

        assert "WorkspacePath" not in tool._file_checksums, \
            "WorkspacePath is not a checksum field — no entry must be stored"


# ---------------------------------------------------------------------------
# TestRunValidationSkipLogic
# ---------------------------------------------------------------------------

class TestRunValidationSkipLogic:
    """Tests for the checksum-based validation-skip in run_validation."""

    @pytest.mark.unit
    def test_first_call_without_cache_always_runs_validation(self):
        """run_validation calls validate_all when _last_validation_result is None."""
        tool = _make_tool()
        assert tool._last_validation_result is None  # precondition

        mock_result = MagicMock(is_valid=True, errors=[], warnings=[])
        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        mock_cls.return_value.validate_all.assert_called_once()

    @pytest.mark.unit
    def test_matching_checksums_and_cached_result_skips_validate_all(self):
        """run_validation skips validate_all when all 5 checksums match and cache exists."""
        tool = _make_tool()
        tool._last_validation_result = MagicMock(is_valid=True, errors=[], warnings=[])
        _set_matching_checksums(tool)

        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            tool.run_validation()

        mock_cls.return_value.validate_all.assert_not_called()

    @pytest.mark.unit
    def test_changed_checksum_triggers_revalidation(self):
        """run_validation calls validate_all when one file checksum has changed."""
        tool = _make_tool()
        tool._last_validation_result = MagicMock(is_valid=True, errors=[], warnings=[])
        _set_matching_checksums(tool)
        # Simulate externally modified file — HuPath checksum differs
        tool._file_checksums["HuPath"] = "new_checksum_after_file_edit"

        mock_result = MagicMock(is_valid=True, errors=[], warnings=[])
        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        mock_cls.return_value.validate_all.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_checksum_field_prevents_skip(self):
        """run_validation does not skip when any checksum is empty (file not yet checked)."""
        tool = _make_tool()
        tool._last_validation_result = MagicMock(is_valid=True, errors=[], warnings=[])
        _set_matching_checksums(tool)
        # FilterPath was never path-checked — remove its entry
        del tool._file_checksums["FilterPath"]
        del tool._validated_checksums["FilterPath"]

        mock_result = MagicMock(is_valid=True, errors=[], warnings=[])
        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        mock_cls.return_value.validate_all.assert_called_once()

    @pytest.mark.unit
    def test_after_validation_validated_checksums_snapshot_is_updated(self):
        """run_validation snapshots _file_checksums into _validated_checksums after a run."""
        tool = _make_tool()
        for field in _ALL_CHECKSUM_FIELDS:
            tool._file_checksums[field] = f"cs_{field}"

        mock_result = MagicMock(is_valid=True, errors=[], warnings=[])
        with patch("ibtool.ibtool.ibtool.InputValidator") as mock_cls, \
             patch("ibtool.ibtool.ibtool.logger"):
            mock_cls.return_value.validate_all.return_value = mock_result
            tool.run_validation()

        assert tool._validated_checksums == tool._file_checksums, \
            "_validated_checksums must mirror _file_checksums after validation"
        assert tool._last_validation_result is mock_result


# ---------------------------------------------------------------------------
# TestSaveConfigChecksumPersistence
# ---------------------------------------------------------------------------

# pylint: disable=invalid-name
class TestSaveConfigChecksumPersistence:
    """Tests for checksum and validation-cache serialisation in _save_config_from_ui."""

    @pytest.mark.unit
    def test_file_checksums_passed_to_update_config(self):
        """_save_config_from_ui forwards _file_checksums to update_config as checksum keys."""
        tool = _make_tool()
        tool._file_checksums = {
            "HuPath":     "aaa111",
            "RnPath":     "bbb222",
            "PartPath":   "ccc333",
            "AuxPath":    "ddd444",
            "FilterPath": "eee555",
        }

        captured = []
        def capture(**kwargs):
            captured.append(kwargs)

        with patch.object(tool.config_manager, "update_config", side_effect=capture), \
             patch.object(tool.config_manager, "save_config"):
            tool._save_config_from_ui()

        # Find the call that contains input_data
        inp_call = next((c for c in captured if "input_data" in c), None)
        assert inp_call is not None, "update_config must be called with input_data"
        inp = inp_call["input_data"]
        assert inp.get("building_footprints_checksum") == "aaa111"
        assert inp.get("road_network_checksum") == "bbb222"
        assert inp.get("partitions_checksum") == "ccc333"
        assert inp.get("aux_layer_checksum") == "ddd444"
        assert inp.get("filter_file_checksum") == "eee555"

    @pytest.mark.unit
    def test_validation_cache_serialised_when_result_is_cached(self):
        """_save_config_from_ui writes JSON-serialised errors/warnings when cache present."""
        import json
        tool = _make_tool()
        result = MagicMock()
        result.errors = ["path error A"]
        result.warnings = ["warning B"]
        tool._last_validation_result = result

        captured = []
        def capture(**kwargs):
            captured.append(kwargs)

        with patch.object(tool.config_manager, "update_config", side_effect=capture), \
             patch.object(tool.config_manager, "save_config"):
            tool._save_config_from_ui()

        cache_call = next((c for c in captured if "validation_cache" in c), None)
        assert cache_call is not None, \
            "update_config must be called with validation_cache when result is cached"
        vc = cache_call["validation_cache"]
        assert json.loads(vc["errors"]) == ["path error A"]
        assert json.loads(vc["warnings"]) == ["warning B"]

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_no_validation_cache_call_when_result_is_none(self):
        """_save_config_from_ui omits the validation_cache update_config call when no cache."""
        tool = _make_tool()
        assert tool._last_validation_result is None  # precondition

        captured = []
        def capture(**kwargs):
            captured.append(kwargs)

        with patch.object(tool.config_manager, "update_config", side_effect=capture), \
             patch.object(tool.config_manager, "save_config"):
            tool._save_config_from_ui()

        cache_calls = [c for c in captured if "validation_cache" in c]
        assert len(cache_calls) == 0, \
            "No validation_cache update must be issued when _last_validation_result is None"


# ---------------------------------------------------------------------------
# TestApplyConfigChecksumRestore
# ---------------------------------------------------------------------------

class TestApplyConfigChecksumRestore:
    """Tests for _validated_checksums and _last_validation_result restore in _apply_config_to_ui."""

    def _make_mock_cfg(self, checksums=None, errors="[]", warnings="[]"):
        """Build a minimal mock PluginConfig with checksum and cache fields set."""
        mock_cfg = MagicMock()
        mock_cfg.ui.auto_load_last_used = True
        mock_cfg.ui.log_level = "INFO"
        mock_cfg.processing.crs_epsg = 0
        mock_cfg.processing.part_start = 0
        mock_cfg.processing.part_end = 0
        mock_cfg.processing.part_list = ""
        mock_cfg.processing.min_building_count = 0
        mock_cfg.processing.min_overlap_blocks = 0
        mock_cfg.processing.global_footprint_density = 0
        mock_cfg.processing.min_area = 0
        mock_cfg.processing.min_patch_size = 0
        mock_cfg.processing.max_hole_size = 0
        mock_cfg.processing.max_gap_size = 0
        mock_cfg.processing.debug_mode = False
        mock_cfg.processing.delete_part_log = False
        mock_cfg.input_data.filter_file_path = ""

        cs = checksums or {}
        mock_cfg.input_data.building_footprints_checksum = cs.get("HuPath", "")
        mock_cfg.input_data.road_network_checksum = cs.get("RnPath", "")
        mock_cfg.input_data.partitions_checksum = cs.get("PartPath", "")
        mock_cfg.input_data.aux_layer_checksum = cs.get("AuxPath", "")
        mock_cfg.input_data.filter_file_checksum = cs.get("FilterPath", "")

        mock_cfg.validation_cache.errors = errors
        mock_cfg.validation_cache.warnings = warnings
        return mock_cfg

    @pytest.mark.unit
    def test_validated_checksums_populated_from_config(self):
        """_apply_config_to_ui loads all 5 checksum fields into _validated_checksums."""
        tool = _make_tool()
        mock_cfg = self._make_mock_cfg(checksums={
            "HuPath": "hu_aa", "RnPath": "rn_bb",
            "PartPath": "pt_cc", "AuxPath": "ax_dd", "FilterPath": "fl_ee",
        })

        with patch.object(tool.config_manager, "config_exists", return_value=True), \
             patch.object(tool.config_manager, "get_config", return_value=mock_cfg), \
             patch.object(tool.config_manager, "apply_to_ui_elements"), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._apply_config_to_ui()

        assert tool._validated_checksums["HuPath"] == "hu_aa"
        assert tool._validated_checksums["RnPath"] == "rn_bb"
        assert tool._validated_checksums["PartPath"] == "pt_cc"
        assert tool._validated_checksums["AuxPath"] == "ax_dd"
        assert tool._validated_checksums["FilterPath"] == "fl_ee"

    @pytest.mark.unit
    def test_validation_result_restored_from_valid_json_cache(self):
        """_apply_config_to_ui restores ValidationResult from valid JSON in validation_cache."""
        import json
        tool = _make_tool()
        tool._last_validation_result = None

        mock_cfg = self._make_mock_cfg(
            errors=json.dumps(["path missing"]),
            warnings=json.dumps(["feature count low"]),
        )

        with patch.object(tool.config_manager, "config_exists", return_value=True), \
             patch.object(tool.config_manager, "get_config", return_value=mock_cfg), \
             patch.object(tool.config_manager, "apply_to_ui_elements"), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._apply_config_to_ui()

        assert tool._last_validation_result is not None
        assert tool._last_validation_result.errors == ["path missing"]
        assert tool._last_validation_result.warnings == ["feature count low"]

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_corrupt_json_in_cache_does_not_crash(self):
        """_apply_config_to_ui silently ignores corrupt JSON in validation_cache."""
        tool = _make_tool()
        tool._last_validation_result = None

        mock_cfg = self._make_mock_cfg(errors="{not: valid json!", warnings="[]")

        with patch.object(tool.config_manager, "config_exists", return_value=True), \
             patch.object(tool.config_manager, "get_config", return_value=mock_cfg), \
             patch.object(tool.config_manager, "apply_to_ui_elements"), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._apply_config_to_ui()  # Must not raise

        assert tool._last_validation_result is None, \
            "Corrupt cache must leave _last_validation_result as None"


# ---------------------------------------------------------------------------
# TestDeleteConfig
# ---------------------------------------------------------------------------

class TestDeleteConfig:
    """Tests for IBTool._delete_config — confirmation, deletion, and UI reset."""

    from helpers.config_manager import ConfigManager as _CM

    @staticmethod
    def _setup_tool_with_tmpdir(tmp_path):
        """Create a tool with its config_manager pointing to tmp_path."""
        from helpers.config_manager import ConfigManager
        tool = _make_tool()
        tool.plugin_dir = str(tmp_path)
        tool.config_manager = ConfigManager(str(tmp_path))
        return tool

    @pytest.mark.unit
    def test_cancel_dialog_does_not_delete_config_file(self, tmp_path):
        """_delete_config leaves CONFIG.ini untouched when the user cancels."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        cfg_file = tmp_path / "CONFIG.ini"
        cfg_file.write_text("[UI]\n", encoding="utf-8")
        tool.config_manager.config_file_path = str(cfg_file)

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.No), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()

        assert cfg_file.exists(), \
            "CONFIG.ini must not be deleted when user cancels the dialog"

    @pytest.mark.unit
    def test_confirm_deletes_config_file(self, tmp_path):
        """_delete_config removes CONFIG.ini when the user confirms."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        cfg_file = tmp_path / "CONFIG.ini"
        cfg_file.write_text("[UI]\n", encoding="utf-8")

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()

        assert not cfg_file.exists(), \
            "CONFIG.ini must be deleted after user confirms"

    @pytest.mark.unit
    def test_confirm_clears_all_path_line_edits(self, tmp_path):
        """_delete_config clears HuPath and all other path fields after confirmation."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        tool.dlg.HuPath.setText("/some/buildings.shp")
        tool.dlg.RnPath.setText("/some/roads.gpkg")
        tool.dlg.WorkspacePath.setText("/some/workspace")

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()

        assert tool.dlg.HuPath.text() == ""
        assert tool.dlg.RnPath.text() == ""
        assert tool.dlg.WorkspacePath.text() == ""

    @pytest.mark.unit
    def test_confirm_resets_all_checksum_caches(self, tmp_path):
        """_delete_config clears _file_checksums, _validated_checksums, and _last_validation_result."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        tool._file_checksums = {"HuPath": "abc"}
        tool._validated_checksums = {"HuPath": "abc"}
        tool._last_validation_result = MagicMock()

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()

        assert tool._file_checksums == {}, \
            "_file_checksums must be empty after reset"
        assert tool._validated_checksums == {}, \
            "_validated_checksums must be empty after reset"
        assert tool._last_validation_result is None, \
            "_last_validation_result must be None after reset"

    @pytest.mark.unit
    def test_confirm_disables_start_button(self, tmp_path):
        """_delete_config disables StartButton after confirmation (re-check required)."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        tool.dlg.set_start_button_ready(True)  # enable it first

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()

        assert not tool.dlg.StartButton.isEnabled(), \
            "StartButton must be disabled after config reset"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_no_config_file_does_not_crash(self, tmp_path):
        """_delete_config does not raise when CONFIG.ini does not exist."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        # No CONFIG.ini created in tmp_path

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger"):
            tool._delete_config()  # Must not raise

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_file_deletion_error_returns_early_without_resetting_fields(self, tmp_path):
        """_delete_config logs CRITICAL and returns early when os.remove raises OSError."""
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        tool = self._setup_tool_with_tmpdir(tmp_path)
        cfg_file = tmp_path / "CONFIG.ini"
        cfg_file.write_text("[UI]\n", encoding="utf-8")
        tool.dlg.HuPath.setText("/some/path.shp")

        with patch("ibtool.ibtool.ibtool.QMessageBox.question",
                   return_value=_QMB.Yes), \
             patch("ibtool.ibtool.ibtool.logger") as mock_log, \
             patch("os.remove", side_effect=OSError("permission denied")):
            tool._delete_config()

        # Must have logged the error at CRITICAL level
        critical_calls = [
            c for c in mock_log.log.call_args_list
            if c[1].get("level") == "CRITICAL"
        ]
        assert len(critical_calls) > 0, \
            "An OSError during deletion must be logged at CRITICAL level"

        # Early return: path fields must not have been cleared
        assert tool.dlg.HuPath.text() == "/some/path.shp", \
            "Path fields must remain unchanged when deletion fails"


# ---------------------------------------------------------------------------
# TestUpdatePhase
# ---------------------------------------------------------------------------

class TestUpdatePhase:
    """Unit tests for IBTool._update_phase."""

    @classmethod
    def setup_class(cls):
        """Set up test fixture with IBTool instance."""
        cls.tool = _make_tool()

    @pytest.mark.unit
    def test_forwards_all_args_to_set_phase_progress(self):
        """Forwards phase, total, name, and percent to dlg.set_phase_progress."""
        with patch.object(self.tool.dlg, "set_phase_progress") as mock_spp:
            self.tool._update_phase(3, 6, "Calculate MST", 40)

        mock_spp.assert_called_once_with(3, 6, "Calculate MST", 40)

    @pytest.mark.unit
    def test_boundary_phase_1_percent_0(self):
        """Does not raise for the first phase at 0 percent."""
        with patch.object(self.tool.dlg, "set_phase_progress") as mock_spp:
            self.tool._update_phase(1, 6, "Load Data", 0)

        mock_spp.assert_called_once_with(1, 6, "Load Data", 0)

    @pytest.mark.unit
    def test_boundary_phase_6_percent_100(self):
        """Does not raise for the last phase at 100 percent."""
        with patch.object(self.tool.dlg, "set_phase_progress") as mock_spp:
            self.tool._update_phase(6, 6, "Save Output", 100)

        mock_spp.assert_called_once_with(6, 6, "Save Output", 100)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_phase_name_does_not_raise(self):
        """Handles an empty phase name without raising."""
        with patch.object(self.tool.dlg, "set_phase_progress"):
            self.tool._update_phase(2, 6, "", 20)  # Must not raise


# ---------------------------------------------------------------------------
# TestLoadInputLayers
# ---------------------------------------------------------------------------

class TestLoadInputLayers:
    """Unit tests for IBTool._load_input_layers (load_to_geopackage and processing.run mocked)."""

    @classmethod
    def setup_class(cls):
        """Set up test fixture with IBTool instance and mock CRS."""
        cls.tool = _make_tool()
        cls.crs = MagicMock()

    def _call_with_mocks(self, _mock_load, _mock_proc):
        """Invoke _load_input_layers with all external deps already patched."""
        return self.tool._load_input_layers(
            "hu.shp", "rn.shp", "aux.shp", "part.shp",
            "/tmp/ws/", self.crs)  # nosec B108 — fake path, all I/O is mocked

    @pytest.mark.unit
    def test_returns_five_element_tuple(self):
        """Returns a tuple of exactly five elements."""
        mock_layer = MagicMock()
        merged = MagicMock()
        with patch("ibtool.ibtool.ibtool.load_to_geopackage", return_value=mock_layer), \
             patch("ibtool.ibtool.ibtool.processing") as mock_proc:
            mock_proc.run.return_value = {"OUTPUT": merged}
            result = self._call_with_mocks(mock_layer, mock_proc)

        assert len(result) == 5, f"Expected 5-element tuple, got {len(result)}"

    @pytest.mark.unit
    def test_calls_load_to_geopackage_four_times(self):
        """Calls load_to_geopackage once per input file (hu, rn, aux, part = 4 total)."""
        mock_layer = MagicMock()
        with patch("ibtool.ibtool.ibtool.load_to_geopackage",
                   return_value=mock_layer) as mock_load, \
             patch("ibtool.ibtool.ibtool.processing") as mock_proc:
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            self._call_with_mocks(mock_load, mock_proc)

        assert mock_load.call_count == 4, \
            f"Expected 4 load_to_geopackage calls, got {mock_load.call_count}"

    @pytest.mark.unit
    def test_creates_spatial_index_on_each_layer(self):
        """Calls createSpatialIndex() once on each of the four loaded layers."""
        mock_layer = MagicMock()
        with patch("ibtool.ibtool.ibtool.load_to_geopackage", return_value=mock_layer), \
             patch("ibtool.ibtool.ibtool.processing") as mock_proc:
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            self._call_with_mocks(mock_layer, mock_proc)

        assert mock_layer.dataProvider().createSpatialIndex.call_count == 4, \
            "createSpatialIndex must be called once per input layer"

    @pytest.mark.unit
    def test_uses_mergevectorlayers_to_combine_aux_and_rn(self):
        """Invokes qgis:mergevectorlayers to merge the aux and rn layers."""
        mock_layer = MagicMock()
        with patch("ibtool.ibtool.ibtool.load_to_geopackage", return_value=mock_layer), \
             patch("ibtool.ibtool.ibtool.processing") as mock_proc:
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            self._call_with_mocks(mock_layer, mock_proc)

        mock_proc.run.assert_called_once()
        assert mock_proc.run.call_args[0][0] == "qgis:mergevectorlayers", \
            "Must use qgis:mergevectorlayers to build the combined line layer"

    @pytest.mark.unit
    def test_aux_layers_line_is_last_tuple_element(self):
        """Returns the merged aux+rn layer as the fifth (last) element."""
        mock_layer = MagicMock()
        merged = MagicMock()
        with patch("ibtool.ibtool.ibtool.load_to_geopackage", return_value=mock_layer), \
             patch("ibtool.ibtool.ibtool.processing") as mock_proc:
            mock_proc.run.return_value = {"OUTPUT": merged}
            result = self._call_with_mocks(mock_layer, mock_proc)

        assert result[4] is merged, \
            "Fifth element must be the merged aux+rn layer (aux_layers_line)"


# ---------------------------------------------------------------------------
# TestRunPartitionPipeline
# ---------------------------------------------------------------------------

_PIPELINE_PARAMS = {
    "min_bdg_count": 5,
    "min_overlap_blocks": 0.3,
    "min_area": 50.0,
    "max_hole_size": 5000.0,
    "max_gap_size": 3000.0,
    "min_patch_size": 1000.0,
    "input_filter": "",
}


class TestRunPartitionPipeline:
    """Unit tests for IBTool._run_partition_pipeline (all external calls mocked)."""

    @classmethod
    def setup_class(cls):
        """Set up test fixture with IBTool instance and mock CRS."""
        cls.tool = _make_tool()
        cls.crs = MagicMock()

    @staticmethod
    def _make_layers():
        return {
            "layer_part": MagicMock(),
            "layer_hu": MagicMock(),
            "layer_rn": MagicMock(),
            "aux_layers_line": MagicMock(),
        }

    def _call(self, layers):
        return self.tool._run_partition_pipeline(
            "PART_01", 1, 5, layers, self.crs,
            "/tmp/ws/", False, 0.5, _PIPELINE_PARAMS)  # nosec B108 — fake path, all I/O is mocked

    # ------------------------------------------------------------------
    # Skip: too few buildings
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_returns_none_when_fewer_than_10_buildings(self):
        """Returns (None, anz_hu) when the partition has fewer than 10 buildings."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 5

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   return_value=sel_hu), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            result, anz_hu = self._call(layers)

        assert result is None, "Must return None layer when < 10 buildings"
        assert anz_hu == 5

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_when_zero_buildings(self):
        """Returns (None, 0) for a partition with no buildings at all."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 0

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   return_value=sel_hu), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            result, anz_hu = self._call(layers)

        assert result is None
        assert anz_hu == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_exactly_10_buildings_is_not_skipped(self):
        """Proceeds when partition has exactly 10 buildings (boundary — not < 10)."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 10
        sel_roads = MagicMock()
        sel_roads.featureCount.return_value = 8
        generic = MagicMock()
        expected = MagicMock()

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   side_effect=[sel_hu, sel_roads, generic, generic]), \
             patch("ibtool.ibtool.ibtool.calc_footprint_density", return_value=0.4), \
             patch("ibtool.ibtool.ibtool.blocker", return_value=generic), \
             patch("ibtool.ibtool.ibtool.input_hu_filter", return_value=generic), \
             patch("ibtool.ibtool.ibtool.identify_dense_blocks", return_value=generic), \
             patch("ibtool.ibtool.ibtool.calculate_mst", return_value=generic), \
             patch("ibtool.ibtool.ibtool.mst_clustering", return_value=generic), \
             patch("ibtool.ibtool.ibtool.add_single_bdg", return_value=generic), \
             patch("ibtool.ibtool.ibtool.edge_catch", return_value=generic), \
             patch("ibtool.ibtool.ibtool.gap_close", return_value=generic), \
             patch("ibtool.ibtool.ibtool.patch_remove", return_value=expected), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": generic}
            result, anz_hu = self._call(layers)

        assert result is expected, \
            "Partition with exactly 10 buildings must not be skipped"
        assert anz_hu == 10

    # ------------------------------------------------------------------
    # Skip: MST failure
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_returns_none_when_mst_calculation_fails(self):
        """Returns (None, anz_hu) when calculate_mst returns None."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 50
        sel_roads = MagicMock()
        sel_roads.featureCount.return_value = 20
        generic = MagicMock()

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   side_effect=[sel_hu, sel_roads, generic, generic]), \
             patch("ibtool.ibtool.ibtool.calc_footprint_density", return_value=0.4), \
             patch("ibtool.ibtool.ibtool.blocker", return_value=generic), \
             patch("ibtool.ibtool.ibtool.input_hu_filter", return_value=generic), \
             patch("ibtool.ibtool.ibtool.identify_dense_blocks", return_value=generic), \
             patch("ibtool.ibtool.ibtool.calculate_mst", return_value=None), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": generic}
            result, anz_hu = self._call(layers)

        assert result is None, "Must return None layer when MST calculation fails"
        assert anz_hu == 50

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_returns_result_layer_and_anz_hu_on_success(self):
        """Returns (patch_remove output, anz_hu) when all pipeline steps succeed."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 30
        sel_roads = MagicMock()
        sel_roads.featureCount.return_value = 12
        generic = MagicMock()
        expected = MagicMock()

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   side_effect=[sel_hu, sel_roads, generic, generic]), \
             patch("ibtool.ibtool.ibtool.calc_footprint_density", return_value=0.4), \
             patch("ibtool.ibtool.ibtool.blocker", return_value=generic), \
             patch("ibtool.ibtool.ibtool.input_hu_filter", return_value=generic), \
             patch("ibtool.ibtool.ibtool.identify_dense_blocks", return_value=generic), \
             patch("ibtool.ibtool.ibtool.calculate_mst", return_value=generic), \
             patch("ibtool.ibtool.ibtool.mst_clustering", return_value=generic), \
             patch("ibtool.ibtool.ibtool.add_single_bdg", return_value=generic), \
             patch("ibtool.ibtool.ibtool.edge_catch", return_value=generic), \
             patch("ibtool.ibtool.ibtool.gap_close", return_value=generic), \
             patch("ibtool.ibtool.ibtool.patch_remove", return_value=expected), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": generic}
            result, anz_hu = self._call(layers)

        assert result is expected, "Must return the patch_remove output layer"
        assert anz_hu == 30, "Must return the building count from sel_hu_layer"

    @pytest.mark.unit
    def test_anz_hu_matches_building_feature_count(self):
        """Returned anz_hu equals sel_hu_layer.featureCount() regardless of skip."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 7  # triggers < 10 skip

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   return_value=sel_hu), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase"):
            mock_proc.run.return_value = {"OUTPUT": MagicMock()}
            _, anz_hu = self._call(layers)

        assert anz_hu == 7, \
            "anz_hu must equal sel_hu_layer.featureCount() even on skip"

    @pytest.mark.unit
    def test_phases_2_through_5_are_updated(self):
        """Calls _update_phase for phases 2, 3, 4, and 5 on a successful run."""
        layers = self._make_layers()
        sel_hu = MagicMock()
        sel_hu.featureCount.return_value = 20
        sel_roads = MagicMock()
        sel_roads.featureCount.return_value = 8
        generic = MagicMock()

        with patch("ibtool.ibtool.ibtool.processing") as mock_proc, \
             patch("ibtool.ibtool.ibtool.select_and_save_by_location",
                   side_effect=[sel_hu, sel_roads, generic, generic]), \
             patch("ibtool.ibtool.ibtool.calc_footprint_density", return_value=0.4), \
             patch("ibtool.ibtool.ibtool.blocker", return_value=generic), \
             patch("ibtool.ibtool.ibtool.input_hu_filter", return_value=generic), \
             patch("ibtool.ibtool.ibtool.identify_dense_blocks", return_value=generic), \
             patch("ibtool.ibtool.ibtool.calculate_mst", return_value=generic), \
             patch("ibtool.ibtool.ibtool.mst_clustering", return_value=generic), \
             patch("ibtool.ibtool.ibtool.add_single_bdg", return_value=generic), \
             patch("ibtool.ibtool.ibtool.edge_catch", return_value=generic), \
             patch("ibtool.ibtool.ibtool.gap_close", return_value=generic), \
             patch("ibtool.ibtool.ibtool.patch_remove", return_value=generic), \
             patch("ibtool.ibtool.ibtool.logger"), \
             patch.object(self.tool, "_update_phase") as mock_phase:
            mock_proc.run.return_value = {"OUTPUT": generic}
            self._call(layers)

        called_phases = [c[0][0] for c in mock_phase.call_args_list]
        assert 2 in called_phases, "_update_phase must be called for phase 2 (Blocks)"
        assert 3 in called_phases, "_update_phase must be called for phase 3 (Filter)"
        assert 4 in called_phases, "_update_phase must be called for phase 4 (MST)"
        assert 5 in called_phases, "_update_phase must be called for phase 5 (Clustering)"
