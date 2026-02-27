"""
Tests for ibtool/ibtool/ibtool.py.

The module exposes three components under test:

  initialize_environment()
    - Sets PYTHONPATH in os.environ and extends sys.path.

  ProcessingThread(QThread)
    - Background thread with progress_update and log_message signals.

  IBTool(iface)
    - Main plugin class; constructor requires a QGIS iface stub and calls
      QSettings to detect the locale.

Unit tests cover (no Processing or real iface operations):
  - initialize_environment: PYTHONPATH env var is set after call
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
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.ibtool.ibtool import IBTool, ProcessingThread, initialize_environment


# ---------------------------------------------------------------------------
# Helper — create IBTool with QSettings mocked to avoid locale issues
# ---------------------------------------------------------------------------

def _make_tool() -> IBTool:
    """Instantiate IBTool with QSettings patched to return a safe locale."""
    with patch("ibtool.ibtool.ibtool.QSettings") as mock_qs:
        mock_qs.return_value.value.return_value = "de_DE"
        return IBTool(_IFACE)


# ---------------------------------------------------------------------------
# TestInitializeEnvironment
# ---------------------------------------------------------------------------

class TestInitializeEnvironment:
    """Unit tests for the module-level initialize_environment function."""

    @pytest.mark.unit
    def test_sets_pythonpath_in_os_environ(self):
        """initialize_environment must set the PYTHONPATH environment variable."""
        initialize_environment()

        assert "PYTHONPATH" in os.environ, \
            "PYTHONPATH must be present in os.environ after initialize_environment()"

    @pytest.mark.unit
    def test_can_be_called_multiple_times_without_crash(self):
        """Calling initialize_environment repeatedly must not raise."""
        initialize_environment()
        initialize_environment()


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

class TestIBTool:
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
        defaults = dict(
            icon_path="",
            text="Test Action",
            callback=lambda: None,
            parent=_PARENT,
        )
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
        """_display_validation_result must log VALIDIERUNG ERFOLGREICH for a fully valid result."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("VALIDIERUNG ERFOLGREICH" in m for m in logged_msgs), \
            "Expected 'VALIDIERUNG ERFOLGREICH' in logged messages"

    @pytest.mark.unit
    def test_errors_are_logged_with_validierungsfehler_header(self):
        """_display_validation_result must log VALIDIERUNGSFEHLER when errors are present."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = False
        result.errors = ["Error A", "Error B"]
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("VALIDIERUNGSFEHLER" in m for m in logged_msgs), \
            "Expected 'VALIDIERUNGSFEHLER' in logged messages"

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
        """_display_validation_result must log WARNUNGEN section when warnings are present."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = ["Minor warning"]

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("WARNUNGEN" in m for m in logged_msgs), \
            "Expected 'WARNUNGEN' in logged messages"

    @pytest.mark.unit
    def test_invalid_result_logs_fehlgeschlagen(self):
        """_display_validation_result must log 'fehlgeschlagen' for an invalid result."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = False
        result.errors = ["Bad path"]
        result.warnings = []

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("fehlgeschlagen" in m for m in logged_msgs), \
            "Expected 'fehlgeschlagen' in logged messages for invalid result"

    @pytest.mark.unit
    def test_valid_with_warnings_logs_bestanden_mit_warnungen(self):
        """_display_validation_result must log 'bestanden (mit Warnungen)' for valid+warnings."""
        tool = _make_tool()
        result = MagicMock()
        result.is_valid = True
        result.errors = []
        result.warnings = ["Non-critical issue"]

        with patch("ibtool.ibtool.ibtool.logger") as mock_logger:
            tool._display_validation_result(result)

        logged_msgs = [call[0][0] for call in mock_logger.log.call_args_list]
        assert any("bestanden" in m for m in logged_msgs), \
            "Expected 'bestanden' in logged messages for valid result with warnings"
