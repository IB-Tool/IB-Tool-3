# -*- coding: utf-8 -*-
"""
Test Module Setup für QGIS Processing Tests - CRASH-PROOF VERSION

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
    """Sicherer Cleanup über atexit - verhindert Crash"""
    global qgis_app
    if qgis_app:
        try:
            # Nur versuchen zu beenden, wenn noch aktiv
            if hasattr(qgis_app, 'exitQgis'):
                qgis_app.exitQgis()
            print("✅ QGIS über atexit sauber beendet")
        except:
            # Alle Fehler ignorieren
            pass
        finally:
            qgis_app = None

def setUpModule():
    """Set up QGIS application for all tests"""
    global qgis_app
    if qgis_app is None:
        # Initialize QGIS application
        from qgis.core import QgsApplication
        
        # GUI=True ist wichtig für Processing!
        qgis_app = QgsApplication([], True)
        qgis_app.setPrefixPath(QGIS_PREFIX_PATH, True)
        qgis_app.initQgis()
        
        # Registriere sicheren Cleanup
        atexit.register(safe_cleanup)
        
        # Initialize processing plugin
        try:
            import processing
            from processing.core.Processing import Processing
            Processing.initialize()
            print("✅ Processing für Tests initialisiert")
        except Exception as e:
            print(f"⚠️ Processing-Setup-Warnung: {e}")

def tearDownModule():
    """Clean up QGIS application - NO-OP Version"""
    # NICHTS TUN - atexit übernimmt das sicher
    print("✅ tearDownModule - Cleanup über atexit")
    pass
