# -*- coding: utf-8 -*-
"""
Test module setup for QGIS Processing tests — crash-proof version.

Supported QGIS versions: 3.40-3.50
"""

import os
import sys
import atexit
from .config import apply_qgis_environment, PROJECT_ROOT, QGIS_PREFIX_PATH

# Add the project root directory to the Python path
project_root = str(PROJECT_ROOT)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure QGIS environment using central config
apply_qgis_environment()

# Global QGIS application instance
qgis_app = None

def safe_cleanup():
    """Safe cleanup registered via atexit — prevents crash on interpreter exit."""
    global qgis_app
    if qgis_app:
        try:
            # Only attempt to exit if still active
            if hasattr(qgis_app, 'exitQgis'):
                qgis_app.exitQgis()
            print("✅ QGIS shut down cleanly via atexit")
        except:
            # Ignore all errors during cleanup
            pass
        finally:
            qgis_app = None

def setUpModule():
    """Set up QGIS application for all tests"""
    global qgis_app
    if qgis_app is None:
        # Initialize QGIS application
        from qgis.core import QgsApplication
        
        # GUI=True is required for Processing algorithm execution
        qgis_app = QgsApplication([], True)
        qgis_app.setPrefixPath(QGIS_PREFIX_PATH, True)
        qgis_app.initQgis()

        # Register safe cleanup to run on interpreter exit
        atexit.register(safe_cleanup)

        # Initialize processing plugin
        try:
            from processing.core.Processing import Processing
            Processing.initialize()
            print("✅ Processing initialized for tests")
        except Exception as e:
            print(f"⚠️ Processing setup warning: {e}")

def tearDownModule():
    """Clean up QGIS application - NO-OP Version"""
    # No-op: atexit handles cleanup safely to prevent crash
    print("✅ tearDownModule — cleanup delegated to atexit")
    pass
