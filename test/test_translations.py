# coding=utf-8
"""Safe Translations Test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""
from .utilities import get_qgis_app

__author__ = 'ismailsunni@yahoo.co.id'
__date__ = '12/10/2011'
__copyright__ = (
    'Copyright 2012, Australia Indonesia Facility for Disaster Reduction'
)
import pytest
import os

from qgis.PyQt.QtCore import QCoreApplication, QTranslator

QGIS_APP = get_qgis_app()


class TestSafeTranslations:
    """Test translations work."""

    def setup_method(self, method):
        """Runs before each test."""
        if 'LANG' in iter(os.environ.keys()):
            os.environ.__delitem__('LANG')

    def teardown_method(self, method):
        """Runs after each test."""
        if 'LANG' in iter(os.environ.keys()):
            os.environ.__delitem__('LANG')

    def test_qgis_translations(self):
        """Test that translations work."""
        parent_path = os.path.join(__file__, os.path.pardir, os.path.pardir)
        dir_path = os.path.abspath(parent_path)
        file_path = os.path.join(dir_path, 'i18n', 'IBTool_de.qm')
        translator = QTranslator()
        
        # Check that the translation file exists on disk
        if not os.path.exists(file_path):
            pytest.fail(f"Translation file not found: {file_path}")

        # Check that the translator loaded the file successfully
        loaded = translator.load(file_path)
        assert loaded, "Failed to load translation file"

        QCoreApplication.installTranslator(translator)

        source_message = 'Cancel'
        expected_translation = 'Abbrechen'
        real_message = QCoreApplication.translate(
            "IBToolDialogBase",
            source_message
        )
        assert expected_translation == real_message