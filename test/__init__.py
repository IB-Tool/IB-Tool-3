# import qgis libs so that ve set the correct sip api version
import qgis   # pylint: disable=W0611  # NOQA

import sys
import os

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# QGIS environment setup
os.environ['QGIS_PREFIX_PATH'] = r'C:\Program Files\QGIS 3.40.0'
os.environ['PYTHONPATH'] = r'C:\Program Files\QGIS 3.40.0\apps\qgis\python'

# Initialize QGIS application for testing
from qgis.core import QgsApplication
from qgis import processing
import unittest

# Global QGIS application instance
qgis_app = None

def setUpModule():
    """Set up QGIS application for all tests"""
    global qgis_app
    if qgis_app is None:
        qgis_app = QgsApplication([], False)
        qgis_app.initQgis()
        
        # Initialize processing plugin
        try:
            from processing.core.Processing import Processing
            Processing.initialize()
        except Exception as e:
            print(f"Warning: Could not initialize Processing plugin: {e}")

def tearDownModule():
    """Clean up QGIS application after all tests"""
    global qgis_app
    if qgis_app:
        qgis_app.exitQgis()
        qgis_app = None