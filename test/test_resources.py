# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'ottmar.hittzfeld@web.de'
__date__ = '2024-12-18'
__copyright__ = 'Copyright 2024, Oliver Harig'

import pytest

from qgis.PyQt.QtGui import QIcon



class TestIBToolResources:
    """Test rerources work."""

    def setup_method(self, method):
        """Runs before each test."""
        pass

    def teardown_method(self, method):
        """Runs after each test."""
        pass

    def test_icon_png(self):
        """Test we can click OK."""
        path = ':/plugins/IBTool/icon.png'
        icon = QIcon(path)
        assert not icon.isNull()




