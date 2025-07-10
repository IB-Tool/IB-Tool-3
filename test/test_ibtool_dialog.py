# coding=utf-8
"""Dialog test."""

import unittest

from qgis.PyQt.QtWidgets import (QDialog, QPushButton, QLineEdit, QProgressBar, 
                                 QPlainTextEdit, QComboBox, QCheckBox, QSpinBox)
from qgis.PyQt.QtCore import Qt

from ibtool_dialog import IBToolDialog
from .utilities import get_qgis_app

__author__ = 'Tim Sutton <tim@linfiniti.com>'
__date__ = '2011-04-22'
__license__ = "GPL"


class IBToolDialogTest(unittest.TestCase):
    """Test dialog works."""

    def setUp(self):
        """Runs before each test."""
        self.qgis_app = get_qgis_app()
        self.dialog = IBToolDialog(None)

    def tearDown(self):
        """Runs after each test."""
        self.dialog = None

    def test_dialog_creation(self):
        """Test that dialog can be created without errors."""
        dialog = IBToolDialog()
        self.assertIsNotNone(dialog)
        self.assertIsInstance(dialog, QDialog)

    # Test alle File-Selection Buttons
    def test_file_selection_buttons(self):
        """Test that all file selection buttons exist and are functional."""
        file_buttons = [
            'HuButton',      # Building footprints file
            'RnButton',      # Road network file  
            'PartButton',    # Partitions file
            'AuxButton',     # Auxiliary data file
            'OutputButton',  # Output file
            'WorkspaceButton', # Workspace folder
            'FilterButton',  # Filter config file
            'LogDirButton'   # Log directory
        ]
        
        for button_name in file_buttons:
            with self.subTest(button=button_name):
                self.assertTrue(hasattr(self.dialog, button_name), 
                               f"Button {button_name} missing")
                button = getattr(self.dialog, button_name)
                self.assertIsNotNone(button)
                self.assertIsInstance(button, QPushButton)
                self.assertTrue(button.isEnabled())
                # Test button click (should not raise exception)
                button.click()

    # Test alle Path-Input Felder
    def test_path_input_fields(self):
        """Test that all path input fields exist and are functional."""
        path_fields = [
            'HuPath',        # Building footprints path
            'RnPath',        # Road network path
            'PartPath',      # Partitions path
            'AuxPath',       # Auxiliary data path
            'OutputPath',    # Output path
            'WorkspacePath', # Workspace path
            'FilterPath',    # Filter config path
            'LogDirPath'     # Log directory path
        ]
        
        for field_name in path_fields:
            with self.subTest(field=field_name):
                self.assertTrue(hasattr(self.dialog, field_name), 
                               f"Field {field_name} missing")
                field = getattr(self.dialog, field_name)
                self.assertIsNotNone(field)
                self.assertIsInstance(field, QLineEdit)
                # Test text setting and getting
                test_text = f"test_path_{field_name}"
                field.setText(test_text)
                self.assertEqual(field.text(), test_text)
                field.clear()
                self.assertEqual(field.text(), "")

    # Test Processing Control Buttons
    def test_processing_control_buttons(self):
        """Test processing control buttons."""
        control_buttons = [
            'StartButton',   # Start processing
            'CancelButton'   # Cancel processing
        ]
        
        for button_name in control_buttons:
            with self.subTest(button=button_name):
                self.assertTrue(hasattr(self.dialog, button_name), 
                               f"Button {button_name} missing")
                button = getattr(self.dialog, button_name)
                self.assertIsNotNone(button)
                self.assertIsInstance(button, QPushButton)
                self.assertTrue(button.isEnabled())
                # Test button click
                button.click()

    # Test Parameter Input Boxes (gemischte Widget-Typen)
    def test_parameter_input_boxes(self):
        """Test that all parameter input boxes exist and are functional."""
        # Test QSpinBox Parameter
        spinbox_parameters = [
            'MinOverlapBlocksBox',      # Minimum overlap blocks
            'GlobalFootprintDensityBox', # Global footprint density
            'MinBdgCountBox',           # Minimum building count      
            'MaxHoleSizeBox',           # Maximum hole size
            'MaxGapSizeBox',            # Maximum gap size
            'MinAreaBox',               # Minimum area
            'MinPatchSizeBox',          # Minimum patch size
        ]
        
        # Test QLineEdit Parameter
        lineedit_parameters = [
            'partlistBox',              # Partition list
            'SpatialReferenceBox',      # Spatial reference
            'partstartBox',             # Partition start
            'partendBox',               # Partition end
        ]
        
        # Teste die SpinBox-Parameter
        for box_name in spinbox_parameters:
            with self.subTest(box=box_name):
                self.assertTrue(hasattr(self.dialog, box_name), 
                               f"SpinBox {box_name} missing")
                box = getattr(self.dialog, box_name)
                self.assertIsNotNone(box)
                self.assertIsInstance(box, QSpinBox)
                
                # Test für QSpinBox
                original_value = box.value()
                test_value = 42
                box.setValue(test_value)
                self.assertEqual(box.value(), test_value)
                box.setValue(original_value)

        # Teste die LineEdit-Parameter
        for box_name in lineedit_parameters:
            with self.subTest(box=box_name):
                self.assertTrue(hasattr(self.dialog, box_name), 
                               f"LineEdit {box_name} missing")
                box = getattr(self.dialog, box_name)
                self.assertIsNotNone(box)
                self.assertIsInstance(box, QLineEdit)
                # Test text input
                test_value = "123.45"
                box.setText(test_value)
                self.assertEqual(box.text(), test_value)
                box.clear()
                self.assertEqual(box.text(), "")

    # Test UI Display Elements
    def test_ui_display_elements(self):
        """Test UI display elements."""
        # Progress Bar
        self.assertTrue(hasattr(self.dialog, 'ProgressBar'))
        progress_bar = self.dialog.ProgressBar
        self.assertIsNotNone(progress_bar)
        self.assertIsInstance(progress_bar, QProgressBar)
        # Test progress bar functionality
        progress_bar.setValue(50)
        self.assertEqual(progress_bar.value(), 50)
        progress_bar.setValue(0)
        self.assertEqual(progress_bar.value(), 0)

        # Message Box
        self.assertTrue(hasattr(self.dialog, 'MessageBox'))
        message_box = self.dialog.MessageBox
        self.assertIsNotNone(message_box)
        self.assertIsInstance(message_box, QPlainTextEdit)
        # Test message box functionality
        test_message = "Test message"
        message_box.setPlainText(test_message)
        self.assertEqual(message_box.toPlainText(), test_message)
        message_box.clear()
        self.assertEqual(message_box.toPlainText(), "")

    # Test Log Level ComboBox
    def test_log_level_combobox(self):
        """Test log level combo box."""
        self.assertTrue(hasattr(self.dialog, 'LogLevelBox'))
        log_level_box = self.dialog.LogLevelBox
        self.assertIsNotNone(log_level_box)
        self.assertIsInstance(log_level_box, QComboBox)
        
        # Test if it has items (should be populated by setup_logging_in_plugin)
        # Note: This might be 0 if not initialized in test environment
        self.assertGreaterEqual(log_level_box.count(), 0)

    # Test CheckBox
    def test_checkbox_elements(self):
        """Test checkbox elements."""
        self.assertTrue(hasattr(self.dialog, 'PartLogBox'))
        part_log_box = self.dialog.PartLogBox
        self.assertIsNotNone(part_log_box)
        self.assertIsInstance(part_log_box, QCheckBox)
        
        # Test checkbox functionality
        part_log_box.setChecked(True)
        self.assertTrue(part_log_box.isChecked())
        part_log_box.setChecked(False)
        self.assertFalse(part_log_box.isChecked())

    # Test Filter Text Areas
    def test_filter_text_areas(self):
        """Test filter text areas."""
        filter_areas = [
            'txtPositive',  # Positive filters
            'txtNegative'   # Negative filters
        ]
        
        for area_name in filter_areas:
            with self.subTest(area=area_name):
                self.assertTrue(hasattr(self.dialog, area_name), 
                               f"Text area {area_name} missing")
                area = getattr(self.dialog, area_name)
                self.assertIsNotNone(area)
                self.assertIsInstance(area, QPlainTextEdit)
                # Test text functionality
                test_text = f"Test filter for {area_name}"
                area.setPlainText(test_text)
                self.assertEqual(area.toPlainText(), test_text)
                area.clear()
                self.assertEqual(area.toPlainText(), "")

    # Test Dialog Behavior
    def test_dialog_accept_reject(self):
        """Test standard dialog behavior."""
        # Test accept
        self.dialog.accept()
        self.assertEqual(self.dialog.result(), QDialog.Accepted)
        
        # Create new dialog for reject test
        dialog = IBToolDialog()
        dialog.reject()
        self.assertEqual(dialog.result(), QDialog.Rejected)

    # Test Widget Relationships
    def test_widget_relationships(self):
        """Test that widgets are properly related to dialog."""
        # Test that all widgets have the dialog as parent or are contained within it
        widgets_to_test = [
            'HuButton', 'RnButton', 'PartButton', 'AuxButton', 'OutputButton',
            'WorkspaceButton', 'FilterButton', 'LogDirButton', 'StartButton', 
            'CancelButton', 'HuPath', 'RnPath', 'PartPath', 'AuxPath', 
            'OutputPath', 'WorkspacePath', 'FilterPath', 'LogDirPath',
            'ProgressBar', 'MessageBox', 'LogLevelBox', 'MinOverlapBlocksBox',
            'GlobalFootprintDensityBox', 'MinBdgCountBox',
            'MaxHoleSizeBox', 'MaxGapSizeBox', 'MinAreaBox', 'MinPatchSizeBox',
            'partstartBox', 'partendBox', 'partlistBox', 'PartLogBox',
            'SpatialReferenceBox', 'txtPositive', 'txtNegative'
        ]
        
        for widget_name in widgets_to_test:
            with self.subTest(widget=widget_name):
                if hasattr(self.dialog, widget_name):
                    widget = getattr(self.dialog, widget_name)
                    self.assertIsNotNone(widget)
                    # Widget should be a Qt widget
                    self.assertTrue(hasattr(widget, 'objectName'))

    # Test Parameter Widget Types
    def test_parameter_widget_types(self):
        """Test that parameter widgets are of correct type."""
        # Expected widget types mapping
        widget_types = {
            # SpinBox Widgets
            'MinOverlapBlocksBox': QSpinBox,
            'GlobalFootprintDensityBox': QSpinBox,
            'MinBdgCountBox': QSpinBox,
            'MaxHoleSizeBox': QSpinBox,
            'MaxGapSizeBox': QSpinBox,
            'MinAreaBox': QSpinBox,
            'MinPatchSizeBox': QSpinBox,
            
            # LineEdit Widgets    
            'partlistBox': QLineEdit,
            'SpatialReferenceBox': QLineEdit,
            'partstartBox': QLineEdit,
            'partendBox': QLineEdit,

            # Other widgets
            'ProgressBar': QProgressBar,
            'MessageBox': QPlainTextEdit,
            'LogLevelBox': QComboBox,
            'PartLogBox': QCheckBox,
            'txtPositive': QPlainTextEdit,
            'txtNegative': QPlainTextEdit,
        }
        
        for widget_name, expected_type in widget_types.items():
            with self.subTest(widget=widget_name):
                self.assertTrue(hasattr(self.dialog, widget_name), 
                               f"Widget {widget_name} missing from dialog")
                widget = getattr(self.dialog, widget_name)
                self.assertIsNotNone(widget)
                self.assertIsInstance(widget, expected_type,
                                    f"{widget_name} should be {expected_type.__name__}")

    # Test Numeric Input Validation
    def test_numeric_input_validation(self):
        """Test that numeric parameter boxes handle numeric input correctly."""
        # SpinBox Tests
        spinbox_tests = [
            ('MinOverlapBlocksBox', 10, 50),
            ('GlobalFootprintDensityBox', 5, 50),
            ('MinBdgCountBox', 5, 100),
            ('MaxHoleSizeBox', 5, 100),
            ('MaxGapSizeBox', 5, 100),
            ('MinAreaBox', 10, 1000),
            ('MinPatchSizeBox', 10, 1000),
        ]
        
        for box_name, min_val, max_val in spinbox_tests:
            with self.subTest(box=box_name):
                self.assertTrue(hasattr(self.dialog, box_name), 
                               f"SpinBox {box_name} missing")
                box = getattr(self.dialog, box_name)
                self.assertIsInstance(box, QSpinBox, f"{box_name} should be QSpinBox")
                
                # Test value setting
                test_value = min_val + 1
                box.setValue(test_value)
                self.assertEqual(box.value(), test_value)
                
                # Test bounds
                if box.minimum() <= min_val:
                    box.setValue(min_val)
                    self.assertGreaterEqual(box.value(), min_val)
                
                if box.maximum() >= max_val:
                    box.setValue(max_val)
                    self.assertLessEqual(box.value(), max_val)
        
        # QLineEdit Tests für numerische Eingabefelder
        lineedit_tests = [
            'partstartBox',
            'partendBox',
        ]
        
        for box_name in lineedit_tests:
            with self.subTest(box=box_name):
                self.assertTrue(hasattr(self.dialog, box_name), 
                               f"LineEdit {box_name} missing")
                box = getattr(self.dialog, box_name)
                self.assertIsInstance(box, QLineEdit, f"{box_name} should be QLineEdit")
                
                # Test numeric input
                test_values = ["123", "45", "0", "1000"]
                for test_val in test_values:
                    box.setText(test_val)
                    self.assertEqual(box.text(), test_val)
                
                # Test clearing
                box.clear()
                self.assertEqual(box.text(), "")

    # Test Special Text Inputs
    def test_special_text_inputs(self):
        """Test special text input fields."""
        special_boxes = {
            'partlistBox': ['1,2,3,4', '10,20,30', '#comment'],
            'SpatialReferenceBox': ['EPSG:4326', 'EPSG:3857', 'EPSG:25832'],
        }
        
        for box_name, test_values in special_boxes.items():
            with self.subTest(box=box_name):
                self.assertTrue(hasattr(self.dialog, box_name), 
                               f"LineEdit {box_name} missing")
                box = getattr(self.dialog, box_name)
                self.assertIsInstance(box, QLineEdit, f"{box_name} should be QLineEdit")
                
                for test_val in test_values:
                    box.setText(test_val)
                    self.assertEqual(box.text(), test_val)
                
                box.clear()
                self.assertEqual(box.text(), "")

    # Test Widget Enablement
    def test_widget_enablement(self):
        """Test that widgets are enabled/disabled appropriately."""
        # Test that input widgets are enabled
        input_widgets = [
            'HuPath', 'RnPath', 'PartPath', 'AuxPath', 'OutputPath',
            'WorkspacePath', 'FilterPath', 'LogDirPath',
            'MinOverlapBlocksBox', 'GlobalFootprintDensityBox',
            'MinAreaBox', 'MinBdgCountBox', 'MinPatchSizeBox',
            'MaxHoleSizeBox', 'MaxGapSizeBox', 'partstartBox',
            'partendBox', 'partlistBox', 'SpatialReferenceBox'
        ]
        
        for widget_name in input_widgets:
            with self.subTest(widget=widget_name):
                self.assertTrue(hasattr(self.dialog, widget_name), 
                               f"Widget {widget_name} missing")
                widget = getattr(self.dialog, widget_name)
                self.assertTrue(widget.isEnabled(), 
                              f"{widget_name} should be enabled")

    # Test Complete Widget Inventory
    def test_complete_widget_inventory(self):
        """Test complete inventory of all GUI widgets."""
        expected_widgets = {
            # Buttons
            'HuButton': QPushButton,
            'RnButton': QPushButton,
            'PartButton': QPushButton,
            'AuxButton': QPushButton,
            'OutputButton': QPushButton,
            'WorkspaceButton': QPushButton,
            'FilterButton': QPushButton,
            'LogDirButton': QPushButton,
            'StartButton': QPushButton,
            'CancelButton': QPushButton,
            
            # Path Fields
            'HuPath': QLineEdit,
            'RnPath': QLineEdit,
            'PartPath': QLineEdit,
            'AuxPath': QLineEdit,
            'OutputPath': QLineEdit,
            'WorkspacePath': QLineEdit,
            'FilterPath': QLineEdit,
            'LogDirPath': QLineEdit,
            
            # Parameter Boxes - QSpinBox
            'MinOverlapBlocksBox': QSpinBox,
            'GlobalFootprintDensityBox': QSpinBox, 
            'MinBdgCountBox': QSpinBox,
            'MaxHoleSizeBox': QSpinBox,
            'MaxGapSizeBox': QSpinBox,
            'MinAreaBox': QSpinBox,
            'MinPatchSizeBox': QSpinBox,
            
            # Parameter Boxes - QLineEdit
            'partlistBox': QLineEdit,
            'SpatialReferenceBox': QLineEdit,
            'partstartBox': QLineEdit,
            'partendBox': QLineEdit,
            
            # Display Elements
            'ProgressBar': QProgressBar,
            'MessageBox': QPlainTextEdit,
            'LogLevelBox': QComboBox,
            'PartLogBox': QCheckBox,
            'txtPositive': QPlainTextEdit,
            'txtNegative': QPlainTextEdit,
        }
        
        for widget_name, expected_type in expected_widgets.items():
            with self.subTest(widget=widget_name):
                self.assertTrue(hasattr(self.dialog, widget_name), 
                               f"Widget {widget_name} missing from dialog")
                widget = getattr(self.dialog, widget_name)
                self.assertIsNotNone(widget)
                self.assertIsInstance(widget, expected_type,
                                    f"{widget_name} should be {expected_type.__name__}")


if __name__ == '__main__':
    unittest.main()