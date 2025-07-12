# import qgis libs so that ve set the correct sip api version
import qgis  # pylint: disable=W0611  # NOQA

import sys
import os

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set environment variables for headless mode
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DISPLAY'] = ':99'

# QGIS environment setup - remove Windows-specific paths
# os.environ['QGIS_PREFIX_PATH'] = r'C:\Program Files\QGIS 3.40.0'
# os.environ['PYTHONPATH'] = r'C:\Program Files\QGIS 3.40.0\apps\qgis\python'

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
        # Create QgsApplication with headless mode
        qgis_app = QgsApplication([], False)

        # Set up application paths for Docker environment
        qgis_app.setPrefixPath('/usr', True)

        # Initialize QGIS
        qgis_app.initQgis()

        # Initialize processing plugin - WICHTIG für Ihre Tools!
        try:
            # Stelle sicher, dass Processing-Plugin verfügbar ist
            from qgis import processing
            from processing.core.Processing import Processing
            Processing.initialize()
            print("Processing plugin initialized successfully")
        except ImportError as e:
            print(f"Critical: Could not import processing module: {e}")
            print("This will cause failures in tool modules!")
        except Exception as e:
            print(f"Warning: Could not initialize Processing plugin: {e}")


def tearDownModule():
    """Clean up QGIS application after all tests"""
    global qgis_app
    if qgis_app:
        qgis_app.exitQgis()
        qgis_app = None