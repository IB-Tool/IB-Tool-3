# coding=utf-8
"""
Tests for ibtool/ibtool_dialog.py — IBToolDialog widget structure and behaviour.

IBToolDialog is a thin UI wrapper (setupUi only, no custom logic).
These tests verify:
  - All expected widgets exist and have the correct Qt type
  - Default values match the .ui file definitions
  - Widgets accept input correctly (setText / setValue / setChecked)
  - Tab widget structure is intact
  - Dialog accept / reject behaviour is correct
  - Buttons outside tabs (Start, Cancel, CheckButton, SaveConfigButton)
"""

import pytest

from qgis.PyQt.QtWidgets import (
    QDialog,
    QPushButton,
    QLineEdit,
    QProgressBar,
    QPlainTextEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QStackedWidget,
)
from qgis.gui import QgsProjectionSelectionWidget

from ibtool.ibtool.ibtool_dialog import IBToolDialog
from .utilities import get_qgis_app

# QGIS must be initialised before any Qt widget is created
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()


# ---------------------------------------------------------------------------
# Fixtures / shared setup
# ---------------------------------------------------------------------------

class TestIBToolDialog:
    """Tests for IBToolDialog widget structure and default values."""

    # Log levels as defined in ibtool.py (setup_logging_in_plugin / run).
    # The .ui has no items; they are added at runtime, so tests seed them here.
    _LOG_LEVELS = ['INFO', 'WARNING', 'CRITICAL', 'SUCCESS']
    _LOG_LEVEL_DEFAULT = 'INFO'

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)
        # Mirror what setup_logging_in_plugin / run() do at runtime
        self.dialog.LogLevelBox.addItems(self._LOG_LEVELS)
        self.dialog.LogLevelBox.setCurrentText(self._LOG_LEVEL_DEFAULT)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    # -----------------------------------------------------------------------
    # Creation
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    def test_dialog_can_be_created(self):
        """IBToolDialog can be instantiated without errors."""
        assert self.dialog is not None
        assert isinstance(self.dialog, QDialog)

    @pytest.mark.unit
    def test_dialog_has_stacked_widget(self):
        """The main stacked widget (stackedWidget) is present after UI modernisation."""
        assert hasattr(self.dialog, "stackedWidget")
        assert isinstance(self.dialog.stackedWidget, QStackedWidget)

    @pytest.mark.unit
    def test_stacked_widget_has_four_pages(self):
        """stackedWidget exposes exactly 4 pages (Eingabe, Parameter, Validierung, Verarbeitung)."""
        assert self.dialog.stackedWidget.count() == 4

    # -----------------------------------------------------------------------
    # Path input widgets (Tab 1 — Datenpfade)
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "HuPath", "RnPath", "PartPath", "AuxPath",
        "OutputPath", "WorkspacePath", "FilterPath", "LogDirPath",
    ])
    def test_path_lineedit_exists_and_is_qlineedit(self, name):
        """All 8 path input fields exist and are QLineEdit."""
        assert hasattr(self.dialog, name), f"Missing widget: {name}"
        assert isinstance(getattr(self.dialog, name), QLineEdit)

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "HuPath", "RnPath", "PartPath", "AuxPath",
        "OutputPath", "WorkspacePath", "FilterPath", "LogDirPath",
    ])
    def test_path_lineedit_accepts_and_clears_text(self, name):
        """Path fields accept setText and clear correctly."""
        widget = getattr(self.dialog, name)
        widget.setText(f"/test/{name}")
        assert widget.text() == f"/test/{name}"
        widget.clear()
        assert widget.text() == ""

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "HuButton", "RnButton", "PartButton", "AuxButton",
        "OutputButton", "WorkspaceButton", "FilterButton", "LogDirButton",
    ])
    def test_file_select_button_exists_enabled(self, name):
        """All 8 file-select buttons exist, are QPushButton, and are enabled."""
        assert hasattr(self.dialog, name), f"Missing button: {name}"
        btn = getattr(self.dialog, name)
        assert isinstance(btn, QPushButton)
        assert btn.isEnabled()

    # -----------------------------------------------------------------------
    # Parameter spinboxes (Tab 2 — Parameter)
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "MinOverlapBlocksBox",
        "GlobalFootprintDensityBox",
        "MinBdgCountBox",
        "MinAreaBox",
        "MinPatchSizeBox",
        "MaxHoleSizeBox",
        "MaxGapSizeBox",
    ])
    def test_spinbox_exists_and_is_qspinbox(self, name):
        """All 7 parameter spinboxes exist and are QSpinBox."""
        assert hasattr(self.dialog, name), f"Missing spinbox: {name}"
        assert isinstance(getattr(self.dialog, name), QSpinBox)

    @pytest.mark.unit
    @pytest.mark.parametrize("name", [
        "MinOverlapBlocksBox",
        "GlobalFootprintDensityBox",
        "MinBdgCountBox",
        "MinAreaBox",
        "MinPatchSizeBox",
        "MaxHoleSizeBox",
        "MaxGapSizeBox",
    ])
    def test_spinbox_accepts_and_restores_value(self, name):
        """SpinBoxes store set values within their bounds."""
        box = getattr(self.dialog, name)
        original = box.value()
        # Use a value well within any spinbox range
        test_val = min(box.maximum(), max(box.minimum(), 42))
        box.setValue(test_val)
        assert box.value() == test_val
        box.setValue(original)

    # -----------------------------------------------------------------------
    # Settings tab (Tab 3)
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    def test_log_level_combobox_exists(self):
        """LogLevelBox exists and is a QComboBox."""
        assert hasattr(self.dialog, "LogLevelBox")
        assert isinstance(self.dialog.LogLevelBox, QComboBox)

    @pytest.mark.unit
    def test_log_level_combobox_has_four_items(self):
        """LogLevelBox contains exactly 4 log-level entries (seeded in setup_method)."""
        assert self.dialog.LogLevelBox.count() == 4

    @pytest.mark.unit
    def test_log_level_combobox_contains_expected_levels(self):
        """LogLevelBox items include INFO, WARNING, CRITICAL, SUCCESS."""
        box = self.dialog.LogLevelBox
        items = [box.itemText(i) for i in range(box.count())]
        for level in ("INFO", "WARNING", "CRITICAL", "SUCCESS"):
            assert level in items, f"Log level '{level}' missing from LogLevelBox"

    @pytest.mark.unit
    def test_log_level_default_is_info(self):
        """LogLevelBox default selection is INFO (set at runtime by setup_logging_in_plugin)."""
        assert self.dialog.LogLevelBox.currentText() == "INFO"

    @pytest.mark.unit
    def test_spatial_reference_box_is_projection_widget(self):
        """SpatialReferenceBox is a QgsProjectionSelectionWidget (not a plain QLineEdit)."""
        assert hasattr(self.dialog, "SpatialReferenceBox")
        assert isinstance(self.dialog.SpatialReferenceBox, QgsProjectionSelectionWidget)

    @pytest.mark.unit
    def test_spatial_reference_box_accepts_crs(self):
        """SpatialReferenceBox accepts and returns a CRS via setCrs / crs()."""
        from qgis.core import QgsCoordinateReferenceSystem
        box = self.dialog.SpatialReferenceBox
        box.setCrs(QgsCoordinateReferenceSystem("EPSG:25833"))
        assert box.crs().authid() == "EPSG:25833"

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["partstartBox", "partendBox", "partlistBox"])
    def test_partition_lineedit_exists(self, name):
        """Partition input fields exist and are QLineEdit."""
        assert hasattr(self.dialog, name), f"Missing widget: {name}"
        assert isinstance(getattr(self.dialog, name), QLineEdit)

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["partstartBox", "partendBox", "partlistBox"])
    def test_partition_lineedit_accepts_text(self, name):
        """Partition input fields accept and clear text."""
        widget = getattr(self.dialog, name)
        widget.setText("42")
        assert widget.text() == "42"
        widget.clear()
        assert widget.text() == ""

    @pytest.mark.unit
    def test_part_log_box_exists_and_is_checkbox(self):
        """PartLogBox (delete partition log) exists and is a QCheckBox."""
        assert hasattr(self.dialog, "PartLogBox")
        assert isinstance(self.dialog.PartLogBox, QCheckBox)

    @pytest.mark.unit
    def test_part_log_box_default_is_checked(self):
        """PartLogBox is checked by default (as defined in .ui file)."""
        assert self.dialog.PartLogBox.isChecked()

    @pytest.mark.unit
    def test_part_log_box_can_be_toggled(self):
        """PartLogBox can be programmatically checked and unchecked."""
        box = self.dialog.PartLogBox
        box.setChecked(False)
        assert not box.isChecked()
        box.setChecked(True)
        assert box.isChecked()

    @pytest.mark.unit
    def test_debug_mode_box_exists_and_is_checkbox(self):
        """DebugModeBox exists and is a QCheckBox."""
        assert hasattr(self.dialog, "DebugModeBox"), \
            "DebugModeBox missing — was it added in the recent commit?"
        assert isinstance(self.dialog.DebugModeBox, QCheckBox)

    @pytest.mark.unit
    def test_debug_mode_box_default_is_unchecked(self):
        """DebugModeBox is unchecked by default (as defined in .ui file)."""
        assert not self.dialog.DebugModeBox.isChecked()

    @pytest.mark.unit
    def test_debug_mode_box_can_be_toggled(self):
        """DebugModeBox can be programmatically toggled."""
        box = self.dialog.DebugModeBox
        box.setChecked(True)
        assert box.isChecked()
        box.setChecked(False)
        assert not box.isChecked()

    # -----------------------------------------------------------------------
    # Filter tab (Tab 4 — Filtering)
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["txtPositive", "txtNegative"])
    def test_filter_text_area_exists(self, name):
        """Filter text areas exist and are QPlainTextEdit."""
        assert hasattr(self.dialog, name), f"Missing widget: {name}"
        assert isinstance(getattr(self.dialog, name), QPlainTextEdit)

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["txtPositive", "txtNegative"])
    def test_filter_text_area_accepts_and_clears_text(self, name):
        """Filter text areas accept setPlainText and clear correctly."""
        widget = getattr(self.dialog, name)
        widget.setPlainText("31001_1000, Wohnhaus")
        assert "31001_1000" in widget.toPlainText()
        widget.clear()
        assert widget.toPlainText() == ""

    # -----------------------------------------------------------------------
    # Main-dialog widgets (outside tabs)
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    def test_start_button_exists_and_enabled(self):
        """StartButton exists, is a QPushButton, and is enabled."""
        assert hasattr(self.dialog, "StartButton")
        assert isinstance(self.dialog.StartButton, QPushButton)
        assert self.dialog.StartButton.isEnabled()

    @pytest.mark.unit
    def test_cancel_button_exists_and_enabled(self):
        """CancelButton exists, is a QPushButton, and is enabled."""
        assert hasattr(self.dialog, "CancelButton")
        assert isinstance(self.dialog.CancelButton, QPushButton)
        assert self.dialog.CancelButton.isEnabled()

    @pytest.mark.unit
    def test_save_config_button_exists_and_enabled(self):
        """SaveConfigButton exists and is enabled (added in recent commit)."""
        assert hasattr(self.dialog, "SaveConfigButton"), \
            "SaveConfigButton missing — was it added in the recent UI commit?"
        btn = self.dialog.SaveConfigButton
        assert isinstance(btn, QPushButton)
        assert btn.isEnabled()

    @pytest.mark.unit
    def test_check_button_exists_and_enabled(self):
        """CheckButton (input validation) exists and is enabled."""
        assert hasattr(self.dialog, "CheckButton"), "CheckButton missing"
        btn = self.dialog.CheckButton
        assert isinstance(btn, QPushButton)
        assert btn.isEnabled()

    @pytest.mark.unit
    def test_progress_bar_exists(self):
        """ProgressBar exists and is a QProgressBar."""
        assert hasattr(self.dialog, "ProgressBar")
        assert isinstance(self.dialog.ProgressBar, QProgressBar)

    @pytest.mark.unit
    def test_progress_bar_accepts_values(self):
        """ProgressBar accepts values between 0 and 100."""
        bar = self.dialog.ProgressBar
        bar.setValue(50)
        assert bar.value() == 50
        bar.setValue(0)
        assert bar.value() == 0
        bar.setValue(100)
        assert bar.value() == 100

    @pytest.mark.unit
    def test_message_box_exists(self):
        """MessageBox (log output) exists and is a QPlainTextEdit."""
        assert hasattr(self.dialog, "MessageBox")
        assert isinstance(self.dialog.MessageBox, QPlainTextEdit)

    @pytest.mark.unit
    def test_message_box_accepts_text(self):
        """MessageBox accepts text and can be cleared."""
        box = self.dialog.MessageBox
        box.setPlainText("Processing started…")
        assert "Processing" in box.toPlainText()
        box.clear()
        assert box.toPlainText() == ""

    # -----------------------------------------------------------------------
    # Dialog behaviour
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    def test_dialog_accept_sets_accepted_result(self):
        """Calling accept() sets result to QDialog.Accepted."""
        self.dialog.accept()
        assert self.dialog.result() == QDialog.Accepted

    @pytest.mark.unit
    def test_dialog_reject_sets_rejected_result(self):
        """Calling reject() sets result to QDialog.Rejected."""
        dlg = IBToolDialog(None)
        dlg.reject()
        assert dlg.result() == QDialog.Rejected

    # -----------------------------------------------------------------------
    # Complete widget inventory
    # -----------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize("name,expected_type", [
        # File-select buttons
        ("HuButton", QPushButton),
        ("RnButton", QPushButton),
        ("PartButton", QPushButton),
        ("AuxButton", QPushButton),
        ("OutputButton", QPushButton),
        ("WorkspaceButton", QPushButton),
        ("FilterButton", QPushButton),
        ("LogDirButton", QPushButton),
        # Path LineEdits
        ("HuPath", QLineEdit),
        ("RnPath", QLineEdit),
        ("PartPath", QLineEdit),
        ("AuxPath", QLineEdit),
        ("OutputPath", QLineEdit),
        ("WorkspacePath", QLineEdit),
        ("FilterPath", QLineEdit),
        ("LogDirPath", QLineEdit),
        # SpinBoxes
        ("MinOverlapBlocksBox", QSpinBox),
        ("GlobalFootprintDensityBox", QSpinBox),
        ("MinBdgCountBox", QSpinBox),
        ("MinAreaBox", QSpinBox),
        ("MinPatchSizeBox", QSpinBox),
        ("MaxHoleSizeBox", QSpinBox),
        ("MaxGapSizeBox", QSpinBox),
        # Settings — CRS widget (QgsProjectionSelectionWidget, not QLineEdit)
        ("SpatialReferenceBox", QgsProjectionSelectionWidget),
        ("partstartBox", QLineEdit),
        ("partendBox", QLineEdit),
        ("partlistBox", QLineEdit),
        # Settings checkboxes
        ("PartLogBox", QCheckBox),
        ("DebugModeBox", QCheckBox),
        # Settings ComboBox
        ("LogLevelBox", QComboBox),
        # Filter text areas
        ("txtPositive", QPlainTextEdit),
        ("txtNegative", QPlainTextEdit),
        # Main-dialog widgets
        ("StartButton", QPushButton),
        ("CancelButton", QPushButton),
        ("SaveConfigButton", QPushButton),
        ("CheckButton", QPushButton),
        ("ProgressBar", QProgressBar),
        ("MessageBox", QPlainTextEdit),
    ])
    def test_widget_type_inventory(self, name, expected_type):
        """Every widget in the .ui file exists and has the expected Qt type."""
        assert hasattr(self.dialog, name), \
            f"Widget '{name}' missing from IBToolDialog"
        widget = getattr(self.dialog, name)
        assert isinstance(widget, expected_type), \
            f"'{name}' should be {expected_type.__name__}, " \
            f"got {type(widget).__name__}"


# ---------------------------------------------------------------------------
# TestIBToolDialogSetStep — set_step() navigation method
# ---------------------------------------------------------------------------

class TestIBToolDialogSetStep:
    """Tests for IBToolDialog.set_step()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    @pytest.mark.parametrize("index", [0, 1, 2, 3])
    def test_set_step_switches_stacked_widget_page(self, index):
        """set_step(i) sets stackedWidget.currentIndex to i."""
        self.dialog.set_step(index)
        assert self.dialog.stackedWidget.currentIndex() == index

    @pytest.mark.unit
    def test_set_step_active_button_has_bold_style(self):
        """The active step button has bold, blue, underlined styling."""
        self.dialog.set_step(1)
        btn = self.dialog.stepBtn1
        style = btn.styleSheet()
        assert "bold" in style
        assert "1565C0" in style

    @pytest.mark.unit
    def test_set_step_completed_buttons_show_checkmark(self):
        """Steps before the current step show a check-mark prefix."""
        self.dialog.set_step(2)
        assert "✓" in self.dialog.stepBtn0.text()
        assert "✓" in self.dialog.stepBtn1.text()

    @pytest.mark.unit
    def test_set_step_future_buttons_restored_to_normal_style(self):
        """Steps after the current step have default styling (no bold)."""
        self.dialog.set_step(0)
        style = self.dialog.stepBtn3.styleSheet()
        # Should NOT be bold (active style contains 'bold')
        assert "1565C0" not in style

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_set_step_zero_all_future_buttons_normal(self):
        """set_step(0): buttons 1–3 have no active styling."""
        self.dialog.set_step(0)
        for i in range(1, 4):
            btn = getattr(self.dialog, f"stepBtn{i}")
            assert "1565C0" not in btn.styleSheet()


# ---------------------------------------------------------------------------
# TestIBToolDialogFieldStatus — set_field_status / clear_field_statuses
# ---------------------------------------------------------------------------

class TestIBToolDialogFieldStatus:
    """Tests for IBToolDialog.set_field_status() and clear_field_statuses()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    def test_set_field_status_ok_shows_checkmark(self):
        """set_field_status(name, True) sets text to '✓' and green colour."""
        self.dialog.set_field_status("HuPath", True)
        label = self.dialog.HuPathStatus
        assert "✓" in label.text()
        assert "2E7D32" in label.styleSheet()

    @pytest.mark.unit
    def test_set_field_status_error_shows_cross(self):
        """set_field_status(name, False) sets text containing '✗'."""
        self.dialog.set_field_status("HuPath", False)
        label = self.dialog.HuPathStatus
        assert "✗" in label.text()
        assert "C62828" in label.styleSheet()

    @pytest.mark.unit
    def test_set_field_status_error_with_message(self):
        """set_field_status(name, False, msg) shows the message after '✗'."""
        self.dialog.set_field_status("HuPath", False, "File not found")
        assert "File not found" in self.dialog.HuPathStatus.text()

    @pytest.mark.unit
    def test_set_field_status_none_clears_label(self):
        """set_field_status(name, None) clears the text and stylesheet."""
        self.dialog.set_field_status("HuPath", True)
        self.dialog.set_field_status("HuPath", None)
        label = self.dialog.HuPathStatus
        assert label.text() == ""
        assert label.styleSheet() == ""

    @pytest.mark.unit
    def test_set_field_status_unknown_field_does_not_crash(self):
        """set_field_status with an unknown field name must not raise."""
        self.dialog.set_field_status("NonExistentField", True)  # no crash

    @pytest.mark.unit
    def test_clear_field_statuses_resets_all_labels(self):
        """clear_field_statuses() sets every status label to empty text."""
        for name in ["HuPath", "RnPath", "OutputPath"]:
            self.dialog.set_field_status(name, False, "error")
        self.dialog.clear_field_statuses()
        for name in ["HuPath", "RnPath", "OutputPath"]:
            label = getattr(self.dialog, f"{name}Status")
            assert label.text() == ""


# ---------------------------------------------------------------------------
# TestIBToolDialogValidationChecklist
# ---------------------------------------------------------------------------

class TestIBToolDialogValidationChecklist:
    """Tests for IBToolDialog.populate_validation_checklist()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    def test_no_errors_shows_all_passed(self):
        """Empty errors and warnings show a single 'All checks passed' item."""
        self.dialog.populate_validation_checklist([], [])
        assert self.dialog.validationChecklist.count() == 1
        assert "passed" in self.dialog.validationChecklist.item(0).text()

    @pytest.mark.unit
    def test_errors_are_added_to_list(self):
        """Each error string appears as a list item prefixed with ❌."""
        self.dialog.populate_validation_checklist(["Missing HuPath", "Bad CRS"], [])
        items = [self.dialog.validationChecklist.item(i).text()
                 for i in range(self.dialog.validationChecklist.count())]
        assert any("Missing HuPath" in t for t in items)
        assert any("Bad CRS" in t for t in items)

    @pytest.mark.unit
    def test_warnings_are_added_to_list(self):
        """Each warning string appears as a list item prefixed with ⚠️."""
        self.dialog.populate_validation_checklist([], ["AuxPath optional"])
        items = [self.dialog.validationChecklist.item(i).text()
                 for i in range(self.dialog.validationChecklist.count())]
        assert any("AuxPath optional" in t for t in items)

    @pytest.mark.unit
    def test_mixed_errors_and_warnings(self):
        """Errors and warnings are both added when both are non-empty."""
        self.dialog.populate_validation_checklist(["err1"], ["warn1"])
        count = self.dialog.validationChecklist.count()
        assert count == 2

    @pytest.mark.unit
    def test_checklist_is_cleared_on_second_call(self):
        """A second call clears the previous contents."""
        self.dialog.populate_validation_checklist(["e1", "e2"], [])
        self.dialog.populate_validation_checklist([], [])
        assert self.dialog.validationChecklist.count() == 1


# ---------------------------------------------------------------------------
# TestIBToolDialogPhaseProgress
# ---------------------------------------------------------------------------

class TestIBToolDialogPhaseProgress:
    """Tests for IBToolDialog.set_phase_progress()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    def test_phase_label_text_is_set(self):
        """set_phase_progress updates phaseLabel with phase/total and name."""
        self.dialog.set_phase_progress(2, 6, "Clustering", 33)
        assert "2/6" in self.dialog.phaseLabel.text()
        assert "Clustering" in self.dialog.phaseLabel.text()

    @pytest.mark.unit
    def test_progress_bar_value_is_set(self):
        """set_phase_progress sets ProgressBar to the given percent."""
        self.dialog.set_phase_progress(3, 6, "Import", 50)
        assert self.dialog.ProgressBar.value() == 50

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_progress_bar_zero_percent(self):
        """set_phase_progress with 0 % sets ProgressBar to 0."""
        self.dialog.set_phase_progress(1, 6, "Init", 0)
        assert self.dialog.ProgressBar.value() == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_progress_bar_hundred_percent(self):
        """set_phase_progress with 100 % sets ProgressBar to 100."""
        self.dialog.set_phase_progress(6, 6, "Done", 100)
        assert self.dialog.ProgressBar.value() == 100


# ---------------------------------------------------------------------------
# TestIBToolDialogResultActions
# ---------------------------------------------------------------------------

class TestIBToolDialogResultActions:
    """Tests for IBToolDialog.show_result_actions() / hide_result_actions()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    def test_show_result_actions_makes_frame_visible(self):
        """show_result_actions() un-hides resultActionsFrame.

        isVisible() requires the parent window to be shown too, which is
        not the case in unit tests.  isHidden() checks only whether the
        widget itself was explicitly hidden, which is what we care about.
        """
        self.dialog.hide_result_actions()
        self.dialog.show_result_actions()
        assert not self.dialog.resultActionsFrame.isHidden()

    @pytest.mark.unit
    def test_hide_result_actions_hides_frame(self):
        """hide_result_actions() sets resultActionsFrame invisible."""
        self.dialog.show_result_actions()
        self.dialog.hide_result_actions()
        assert not self.dialog.resultActionsFrame.isVisible()


# ---------------------------------------------------------------------------
# TestIBToolDialogStartButton
# ---------------------------------------------------------------------------

class TestIBToolDialogStartButton:
    """Tests for IBToolDialog.set_start_button_ready()."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

    def teardown_method(self, method):
        self.dialog.close()
        self.dialog = None

    @pytest.mark.unit
    def test_set_start_button_ready_true_enables_button(self):
        """set_start_button_ready(True) enables StartButton."""
        self.dialog.set_start_button_ready(True)
        assert self.dialog.StartButton.isEnabled()

    @pytest.mark.unit
    def test_set_start_button_ready_false_disables_button(self):
        """set_start_button_ready(False) disables StartButton."""
        self.dialog.set_start_button_ready(False)
        assert not self.dialog.StartButton.isEnabled()

    @pytest.mark.unit
    def test_set_start_button_ready_true_applies_green_style(self):
        """set_start_button_ready(True) applies a green background to StartButton."""
        self.dialog.set_start_button_ready(True)
        assert "2E7D32" in self.dialog.StartButton.styleSheet()

    @pytest.mark.unit
    def test_set_start_button_ready_false_clears_style(self):
        """set_start_button_ready(False) removes the green style from StartButton."""
        self.dialog.set_start_button_ready(True)
        self.dialog.set_start_button_ready(False)
        assert "2E7D32" not in self.dialog.StartButton.styleSheet()


# ---------------------------------------------------------------------------
# TestIBToolDialogCloseCallback
# ---------------------------------------------------------------------------

class TestIBToolDialogCloseCallback:
    """Tests for IBToolDialog.set_close_callback() and closeEvent."""

    @pytest.mark.unit
    def test_close_callback_is_called_on_close(self):
        """A registered close callback is invoked when the dialog closes."""
        dialog = IBToolDialog(None)
        called = []
        dialog.set_close_callback(lambda: called.append(True))
        dialog.close()
        assert called == [True]

    @pytest.mark.unit
    def test_close_without_callback_does_not_crash(self):
        """Closing a dialog with no registered callback must not raise."""
        dialog = IBToolDialog(None)
        dialog.close()  # no crash

    @pytest.mark.unit
    def test_set_close_callback_stores_callable(self):
        """set_close_callback stores the callable as _close_callback."""
        dialog = IBToolDialog(None)
        fn = lambda: None
        dialog.set_close_callback(fn)
        assert dialog._close_callback is fn
        dialog.close()


# ---------------------------------------------------------------------------
# TestFilterPreviewDialog
# ---------------------------------------------------------------------------

class TestFilterPreviewDialog:
    """Tests for FilterPreviewDialog."""

    @classmethod
    def setup_class(cls):
        # QGIS app already initialised via module-level get_qgis_app()
        pass

    @pytest.mark.unit
    def test_can_be_instantiated(self):
        """FilterPreviewDialog can be created with positive and negative text."""
        from ibtool.ibtool.ibtool_dialog import FilterPreviewDialog
        dlg = FilterPreviewDialog("pos content", "neg content")
        assert dlg is not None
        dlg.close()

    @pytest.mark.unit
    def test_window_title_is_filter_entries(self):
        """FilterPreviewDialog has the window title 'Filter entries'."""
        from ibtool.ibtool.ibtool_dialog import FilterPreviewDialog
        dlg = FilterPreviewDialog("", "")
        assert dlg.windowTitle() == "Filter entries"
        dlg.close()

    @pytest.mark.unit
    def test_minimum_size_is_set(self):
        """FilterPreviewDialog has a minimum width of 700 and height of 450."""
        from ibtool.ibtool.ibtool_dialog import FilterPreviewDialog
        dlg = FilterPreviewDialog("a", "b")
        assert dlg.minimumWidth() >= 700
        assert dlg.minimumHeight() >= 450
        dlg.close()

    @pytest.mark.unit
    def test_reject_closes_dialog(self):
        """Calling reject() on FilterPreviewDialog sets result to Rejected."""
        from ibtool.ibtool.ibtool_dialog import FilterPreviewDialog
        from qgis.PyQt.QtWidgets import QDialog
        dlg = FilterPreviewDialog("a", "b")
        dlg.reject()
        assert dlg.result() == QDialog.Rejected
