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
  - IBTool._apply_config_to_ui: returns early without crash when no config exists
  - IBTool._save_config_from_ui: calls config_manager.update_config and save_config
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
