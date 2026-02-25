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
    QTabWidget,
)

from ibtool.ibtool.ibtool_dialog import IBToolDialog
from .utilities import get_qgis_app

# QGIS must be initialised before any Qt widget is created
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()


# ---------------------------------------------------------------------------
# Fixtures / shared setup
# ---------------------------------------------------------------------------

class TestIBToolDialog:
    """Tests for IBToolDialog widget structure and default values."""

    def setup_method(self, method):
        self.dialog = IBToolDialog(None)

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
    def test_dialog_has_tab_widget(self):
        """The main tab widget (tabWidget) is present."""
        assert hasattr(self.dialog, "tabWidget")
        assert isinstance(self.dialog.tabWidget, QTabWidget)

    @pytest.mark.unit
    def test_tab_widget_has_four_tabs(self):
        """tabWidget exposes exactly 4 tabs (Datenpfade, Parameter, Settings, Filtering)."""
        assert self.dialog.tabWidget.count() == 4

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
        """LogLevelBox contains exactly 4 log-level entries."""
        assert self.dialog.LogLevelBox.count() == 4

    @pytest.mark.unit
    def test_log_level_combobox_contains_expected_levels(self):
        """LogLevelBox items include WARNING, CRITICAL, SUCCESS, INFO."""
        box = self.dialog.LogLevelBox
        items = [box.itemText(i) for i in range(box.count())]
        for level in ("WARNING", "CRITICAL", "SUCCESS", "INFO"):
            assert level in items, f"Log level '{level}' missing from LogLevelBox"

    @pytest.mark.unit
    def test_log_level_default_is_warning(self):
        """LogLevelBox default selection is WARNING (as defined in .ui file)."""
        assert self.dialog.LogLevelBox.currentText() == "WARNING"

    @pytest.mark.unit
    def test_spatial_reference_box_default(self):
        """SpatialReferenceBox defaults to 'EPSG:25832' as defined in .ui."""
        assert hasattr(self.dialog, "SpatialReferenceBox")
        assert self.dialog.SpatialReferenceBox.text() == "EPSG:25832"

    @pytest.mark.unit
    def test_spatial_reference_box_accepts_text(self):
        """SpatialReferenceBox can be changed and cleared."""
        box = self.dialog.SpatialReferenceBox
        box.setText("EPSG:25833")
        assert box.text() == "EPSG:25833"
        box.clear()
        assert box.text() == ""

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
        # Settings LineEdits
        ("SpatialReferenceBox", QLineEdit),
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
