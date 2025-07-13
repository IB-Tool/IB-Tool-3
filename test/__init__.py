# -*- coding: utf-8 -*-
"""
Test Module Setup für QGIS Processing Tests - CRASH-PROOF VERSION

Supported QGIS versions: 3.40-3.50
"""

import os
import sys
import atexit

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# QGIS environment setup
qgis_root = r'C:\Program Files\QGIS 3.40.0'
os.environ['QGIS_PREFIX_PATH'] = qgis_root
os.environ['PYTHONPATH'] = os.path.join(qgis_root, 'apps', 'qgis', 'python')

# Füge alle notwendigen QGIS-Pfade hinzu
qgis_paths = [
    os.path.join(qgis_root, 'apps', 'qgis', 'python'),
    os.path.join(qgis_root, 'apps', 'qgis', 'python', 'plugins'),
    os.path.join(qgis_root, 'apps', 'Python312', 'Lib', 'site-packages'),
]

for path in qgis_paths:
    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

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
        qgis_app.setPrefixPath(qgis_root, True)
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