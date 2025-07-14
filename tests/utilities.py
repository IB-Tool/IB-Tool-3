# coding=utf-8
"""Common functionality used by regression tests."""

import sys
import logging
import os

LOGGER = logging.getLogger('QGIS')
QGIS_APP = None  # Static variable used to hold hand to running QGIS app
CANVAS = None
PARENT = None
IFACE = None


def get_qgis_app():
    """ Start one QGIS application to test against.

    :returns: Handle to QGIS app, canvas, iface and parent. If there are any
        errors the tuple members will be returned as None.
    :rtype: (QgsApplication, CANVAS, IFACE, PARENT)

    If QGIS is already running the handle to that app will be returned.
    """

    global QGIS_APP  # pylint: disable=W0603

    if QGIS_APP is None:
        try:
            # Ensure QGIS environment is properly set up
            qgis_root = r'C:\Program Files\QGIS 3.40.0'
            if 'QGIS_PREFIX_PATH' not in os.environ:
                os.environ['QGIS_PREFIX_PATH'] = qgis_root

            # Add QGIS paths to sys.path if not already present
            qgis_paths = [
                os.path.join(qgis_root, 'apps', 'qgis', 'python'),
                os.path.join(qgis_root, 'apps', 'qgis', 'python', 'plugins'),
                os.path.join(qgis_root, 'apps', 'Python312', 'Lib', 'site-packages'),
            ]

            for path in qgis_paths:
                if os.path.exists(path) and path not in sys.path:
                    sys.path.insert(0, path)

            # Import QGIS modules in the correct order
            from qgis.core import QgsApplication

            # Initialize QGIS application FIRST
            gui_flag = True  # All test will run qgis in gui mode
            QGIS_APP = QgsApplication(sys.argv, gui_flag)
            QGIS_APP.setPrefixPath(qgis_root, True)
            QGIS_APP.initQgis()

            # Only import GUI modules AFTER QGIS is initialized
            from qgis.PyQt import QtGui, QtCore
            from qgis.gui import QgsMapCanvas
            from .qgis_interface import QgisInterface

            s = QGIS_APP.showSettings()
            LOGGER.debug(s)

        except ImportError as e:
            LOGGER.error(f"Failed to import QGIS modules: {e}")
            return None, None, None, None
        except Exception as e:
            LOGGER.error(f"Failed to initialize QGIS: {e}")
            return None, None, None, None

    # Setup GUI components only after QGIS is fully initialized
    global PARENT  # pylint: disable=W0603
    if PARENT is None:
        try:
            from qgis.PyQt import QtGui
            PARENT = QtGui.QWidget()
        except ImportError:
            PARENT = None

    global CANVAS  # pylint: disable=W0603
    if CANVAS is None:
        try:
            from qgis.PyQt import QtCore
            from qgis.gui import QgsMapCanvas
            CANVAS = QgsMapCanvas(PARENT)
            CANVAS.resize(QtCore.QSize(400, 400))
        except ImportError:
            CANVAS = None

    global IFACE  # pylint: disable=W0603
    if IFACE is None:
        try:
            from .qgis_interface import QgisInterface
            # QgisInterface is a stub implementation of the QGIS plugin interface
            IFACE = QgisInterface(CANVAS)
        except ImportError:
            IFACE = None

    return QGIS_APP, CANVAS, IFACE, PARENT