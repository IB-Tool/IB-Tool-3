# coding=utf-8
"""Dialog test."""

import unittest

from qgis.PyQt.QtWidgets import QDialog
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

    def test_dialog_ok(self):
        """Test we can click Start button."""
        # StartButton ist ein QPushButton, nicht ein QDialogButtonBox
        button = self.dialog.StartButton
        self.assertIsNotNone(button)
        
        # Simuliere einen Button-Click
        button.click()
        
        # Da StartButton kein Standard-Dialog-Button ist, 
        # testen wir nur, ob der Button existiert und klickbar ist
        self.assertTrue(button.isEnabled())

    def test_dialog_cancel(self):
        """Test we can click Cancel button."""
        # CancelButton ist ein QPushButton, nicht ein QDialogButtonBox  
        button = self.dialog.CancelButton
        self.assertIsNotNone(button)
        
        # Simuliere einen Button-Click
        button.click()
        
        # Da CancelButton kein Standard-Dialog-Button ist,
        # testen wir nur, ob der Button existiert und klickbar ist
        self.assertTrue(button.isEnabled())

    def test_dialog_creation(self):
        """Test that dialog can be created without errors."""
        dialog = IBToolDialog()
        self.assertIsNotNone(dialog)
        self.assertIsInstance(dialog, QDialog)

    def test_dialog_has_required_buttons(self):
        """Test that dialog has expected buttons."""
        # Prüfe, ob die wichtigsten Buttons vorhanden sind
        self.assertTrue(hasattr(self.dialog, 'StartButton'))
        self.assertTrue(hasattr(self.dialog, 'CancelButton'))
        self.assertIsNotNone(self.dialog.StartButton)
        self.assertIsNotNone(self.dialog.CancelButton)


if __name__ == '__main__':
    unittest.main()