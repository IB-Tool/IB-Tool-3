# -*- coding: utf-8 -*-
"""Main plugin class and processing orchestrator for IBTool.

This module contains the ``IBTool`` QGIS plugin class, which owns the plugin
lifecycle (``initGui`` / ``unload``), the 4-step stepper UI dialog, all file-
dialog helpers, input validation, configuration persistence (CONFIG.ini), and
the ``start_processing()`` method that drives the full settlement-delineation
pipeline partition by partition.

Classes:
    ProcessingThread: QThread subclass (currently unused stub — processing runs
        synchronously on the main thread via ``start_processing()``).
    IBTool: Main QGIS plugin class registered via ``classFactory()``.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""

import os
import sys

from qgis._core import QgsFeatureRequest
from qgis.core import QgsProcessingContext

# In der edge_catch4 Funktion:
context = QgsProcessingContext()
context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)


# Constants for configuration
PYTHONPATH = '/helpers'


def initialize_environment():
    """Set up environment variables and system paths."""
    os.environ['PYTHONPATH'] = PYTHONPATH
    sys.path.append(PYTHONPATH)

    qgis_prefix = os.environ.get('QGIS_PREFIX_PATH')
    if not qgis_prefix:
        potential_paths = [
            '/usr',
            '/usr/local',
            '/Applications/QGIS.app/Contents/MacOS'
        ]
        for path in potential_paths:
            if os.path.exists(os.path.join(path, 'bin', 'qgis')) or \
               os.path.exists(os.path.join(path, 'bin', 'qgis.bin')):
                qgis_prefix = path
                break

    if qgis_prefix:
        os.environ['PATH'] += os.pathsep + os.path.join(qgis_prefix, 'bin')
        python_path = os.path.join(qgis_prefix, 'share', 'qgis', 'python')
        os.environ['PYTHONPATH'] += os.pathsep + python_path
        if python_path not in sys.path:
            sys.path.append(python_path)


# Initialize the environment
initialize_environment()


from qgis.PyQt.QtCore import (  # noqa: E402
    QCoreApplication,
    QSettings,
    QThread,
    QTranslator,
    pyqtSignal
)
from qgis.PyQt.QtGui import QIcon  # noqa: E402
from qgis.PyQt.QtWidgets import (  # noqa: E402
    QAction,
    QDialog,
    QFileDialog,
    QApplication,
)
from qgis.core import (  # noqa: E402
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsVectorLayer,
    QgsProject,
)
from qgis import processing  # noqa: E402
from ibtool.helpers.logger import Logger as MainLogger  # noqa: E402
from ibtool.helpers.geometry_utils import (  # noqa: E402
    load_to_geopackage,
    select_and_save_by_location,
    create_empty_layer
)
from ibtool.helpers.system_utils import (  # noqa: E402
    manage_directory,
    save_temp_layer_to_gpkg,
    version_check
)
from ibtool.helpers.message import msg  # noqa: E402
from ibtool.helpers.check import InputValidator, ValidationResult  # noqa: E402
from ibtool.helpers.config_manager import ConfigManager  # noqa: E402
from ibtool.helpers.data_loader import create_partitions_list  # noqa: E402

from ibtool.ibtool_tools.FootprintDensity import (  # noqa: E402
    calc_footprint_density,
    identify_dense_blocks
)
from ibtool.ibtool_tools.Blocker import blocker  # noqa: E402
from ibtool.ibtool_tools.ImportFilter import input_hu_filter  # noqa: E402
from ibtool.ibtool_tools.CreateMST import calculate_mst  # noqa: E402
from ibtool.ibtool_tools.MST_Clustering import mst_clustering  # noqa: E402
from ibtool.ibtool_tools.AddSingleBuilding import add_single_bdg  # noqa: E402
from ibtool.ibtool_tools.EdgeCatch import edge_catch  # noqa: E402
from ibtool.ibtool_tools.GapClose import gap_close  # noqa: E402
from ibtool.ibtool_tools.PatchRemove import patch_remove  # noqa: E402

# Import the dialog class
from ibtool.ibtool.ibtool_dialog import IBToolDialog, FilterPreviewDialog  # noqa: E402

# Initialize the logger instance
logger = MainLogger()


class ProcessingThread(QThread):
    """Thread for background processing"""
    progress_update = pyqtSignal(int)
    log_message = pyqtSignal(str)
    phase_update = pyqtSignal(int, int, str)   # phase, total, name
    finished_ok = pyqtSignal(str)              # output_path
    finished_error = pyqtSignal(str)           # error_message

    def run(self):
        """Main processing logic"""
        try:
            for i in range(101):  # Progress from 0 to 100
                self.msleep(50)  # Simulated processing (50 ms delay)
                self.progress_update.emit(i)  # Update progress
                self.log_message.emit(f"Progress: {i}%")  # Send message
        except Exception as e:
            self.log_message.emit(f"Error: {str(e)}")


class IBTool:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Initialise the IBTool plugin instance.

        Args:
            iface: QGIS interface instance that provides access to the QGIS
                application (map canvas, message bar, toolbar, etc.).
        """
        # Save reference to the QGIS interface

        self.iface = iface
        # Initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # Initialize config manager (plugin root is one level above ibtool/ibtool/)
        plugin_root = os.path.dirname(self.plugin_dir)
        self.config_manager = ConfigManager(plugin_root)
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            f'IBTool_{locale}.qm')

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&IB-Tool')

        # Check if plugin was started the first time in the current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        """Initialization of the main class"""
        # Create a new instance of the generated UI class
        self.dlg = IBToolDialog()

        # Link the UI to a QDialog object
        self.dialog = QDialog()  # Create a new QDialog object
        self.dlg.setupUi(self.dialog)  # Link the UI with the dialog

        # Add progress bar and message window
        self.dlg.ProgressBar.setValue(0)  # Set progress to 0
        self.dlg.MessageBox.clear()  # Clear the message window

        # Thread for background processing
        self.thread = ProcessingThread()
        self.thread.progress_update.connect(self.update_progress)
        self.thread.log_message.connect(self.update_messages)

        # Last successful output paths (used by result action buttons)
        self._last_output_path = ""
        self._last_output_folder = ""

    def update_progress(self, value):
        """Update progress bar"""
        self.dlg.ProgressBar.setValue(value)

    def update_messages(self, message):
        """Display messages in the window"""
        self.dlg.MessageBox.appendPlainText(message)

    def cancel_processing(self):
        """Cancel processing"""
        if self.thread.isRunning():
            self.thread.terminate()  # Terminate thread
            self.update_messages("Processing canceled.")

    # noinspection PyMethodMayBeStatic
    def tr(self, message):  # pylint: disable=invalid-name
        """Return the Qt translation for a string.

        Implemented here because IBTool does not inherit QObject.

        Args:
            message: The source string to translate.

        Returns:
            The translated string (or the original if no translation exists).
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('IBTool', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Create a QAction and register it in the QGIS toolbar and menu.

        Args:
            icon_path: File-system or resource path to the action icon.
            text: Label shown in the plugin menu entry.
            callback: Callable invoked when the action is triggered.
            enabled_flag: Whether the action is enabled on creation.
            add_to_menu: Whether to add the action to the plugin menu.
            add_to_toolbar: Whether to add the icon to the plugins toolbar.
            status_tip: Tooltip text shown on mouse hover.
            whats_this: Text shown in the status bar on hover.
            parent: Parent widget for the QAction.

        Returns:
            The newly created ``QAction`` (also appended to ``self.actions``).
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):  # pylint: disable=invalid-name
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = os.path.join(os.path.dirname(self.plugin_dir), 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr(u'IB-Tool'),
            callback=self.run,
            parent=self.iface.mainWindow())

        self.setup_logging_in_plugin()

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&IB-Tool'),
                action)
            self.iface.removeToolBarIcon(action)

        # Logger schließen
        logger.close_logger()

    def setup_logging_in_plugin(self):
        """Populate LogLevelBox and connect it to the logger's set_log_level."""
        valid_levels = ['INFO', 'WARNING', 'CRITICAL', 'SUCCESS']
        self.dlg.LogLevelBox.addItems(valid_levels)

        # Set the default log level
        default_level = 'INFO'
        if default_level in valid_levels:
            self.dlg.LogLevelBox.setCurrentText(default_level)
            logger.set_log_level(default_level)
        else:
            raise ValueError(f"Invalid default log level: {default_level}")

        # Handle log level changes
        def apply_log_level():
            selected_level = self.dlg.LogLevelBox.currentText()
            if selected_level in valid_levels:
                logger.set_log_level(selected_level)
            else:
                msg(f"Invalid log level: {selected_level}")

        self.dlg.LogLevelBox.currentTextChanged.connect(apply_log_level)

    def run(self):  # noqa: F811
        """Run method that performs all the real work"""

        # check version of QGIS and Python
        version_check()

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the
        # plugin is started
        if self.first_start:
            self.first_start = False
            self.dlg = IBToolDialog()
            self.dlg.HuButton.clicked.connect(self.select_hu_file)
            self.dlg.RnButton.clicked.connect(self.select_rn_file)
            self.dlg.PartButton.clicked.connect(self.select_part_file)
            self.dlg.AuxButton.clicked.connect(self.select_aux_file)
            self.dlg.OutputButton.clicked.connect(self.select_output_file)
            self.dlg.WorkspaceButton.clicked.connect(self.select_workspace_file)
            self.dlg.FilterButton.clicked.connect(self.select_filter_file)
            self.dlg.LogDirButton.clicked.connect(self.select_log_dir)
            self.dlg.CheckButton.clicked.connect(self.run_validation)
            self.dlg.StartButton.clicked.connect(self.start_processing)
            self.dlg.CancelButton.clicked.connect(self.cancel_processing)
            self.dlg.SaveConfigButton.clicked.connect(self._save_config_from_ui)
            # Start button disabled by default — requires successful check
            self.dlg.set_start_button_ready(False)
            # Disable Start button when input paths change (re-check required)
            for path_widget in [self.dlg.HuPath, self.dlg.RnPath,
                                self.dlg.PartPath, self.dlg.AuxPath,
                                self.dlg.FilterPath, self.dlg.OutputPath,
                                self.dlg.WorkspacePath]:
                path_widget.textChanged.connect(
                    lambda: self.dlg.set_start_button_ready(False)
                )
            # Populate LogLevel dropdown (setup_logging_in_plugin ran on the
            # old dialog in initGui; this new dialog instance needs items added)
            for _lvl in ['INFO', 'WARNING', 'CRITICAL', 'SUCCESS']:
                self.dlg.LogLevelBox.addItem(_lvl)
            self.dlg.LogLevelBox.setCurrentText('INFO')
            self.dlg.LogLevelBox.currentTextChanged.connect(
                lambda: logger.set_log_level(self.dlg.LogLevelBox.currentText())
            )

            # Step navigation
            self.dlg.backButton.clicked.connect(self._go_prev_step)
            self.dlg.nextButton.clicked.connect(self._go_next_step)
            for i in range(4):
                getattr(self.dlg, f'stepBtn{i}').clicked.connect(
                    lambda checked, idx=i: self.dlg.set_step(idx)
                )

            # Per-field inline path validation
            path_fields = {
                'HuPath': self.dlg.HuPath,
                'RnPath': self.dlg.RnPath,
                'PartPath': self.dlg.PartPath,
                'AuxPath': self.dlg.AuxPath,
                'FilterPath': self.dlg.FilterPath,
                'OutputPath': self.dlg.OutputPath,
                'WorkspacePath': self.dlg.WorkspacePath,
                'LogDirPath': self.dlg.LogDirPath,
            }
            for field_name, widget in path_fields.items():
                widget.textChanged.connect(
                    lambda text, fn=field_name: self._check_path_field(fn, text)
                )

            # Copy log to clipboard
            self.dlg.copyLogButton.clicked.connect(self._copy_log_to_clipboard)

            # Result action buttons (connected once; read from self._last_output_*)
            self.dlg.resultLoadButton.clicked.connect(self._load_result_to_qgis)
            self.dlg.resultOpenDirButton.clicked.connect(self._open_output_dir)
            self.dlg.resultExportLogButton.clicked.connect(self._export_log)

            # Filter preview
            self.dlg.showFilterButton.clicked.connect(self._show_filter_preview)

            # Auto-save config when dialog is closed
            self.dlg.set_close_callback(self._save_config_from_ui)

            # Initialise step indicator on step 0
            self.dlg.set_step(0)

            # Set default CRS (overridden later by _apply_config_to_ui if config exists)
            self.dlg.SpatialReferenceBox.setCrs(QgsCoordinateReferenceSystem("EPSG:25832"))

        # Config aus CONFIG.ini in UI laden
        self._apply_config_to_ui()

        # Automatische Aktualisierung der Textfelder bei Start
        file_path = self.dlg.FilterPath.text()  # Pfad aus dem QLineEdit abrufen
        if file_path and os.path.exists(file_path):  # Prüfen, ob Pfad existiert
            self.load_filter_file(file_path)

        logger.set_message_box(self.dlg.MessageBox)

        self.dlg.MessageBox.clear()
        self.dlg.hide_result_actions()
        # show the dialog
        self.dlg.show()

    def select_hu_file(self):
        """Opens a file dialog to select the HU file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,  # Dialog is part of the GUI
            "Select building footprints file",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if file_path:
            self.dlg.HuPath.setText(file_path)  # Display the path in QLineEdit

    def select_rn_file(self):
        """Opens a file dialog to select the RN file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            "Select road network file",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if file_path:
            self.dlg.RnPath.setText(file_path)  # Display the path in QLineEdit

    def select_part_file(self):
        """Opens a file dialog to select the PART file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            "Select partitions file",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if file_path:
            self.dlg.PartPath.setText(
                file_path)  # Display the path in QLineEdit

    def select_aux_file(self):
        """Opens a file dialog to select the AUX file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            "Select auxiliary data file",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if file_path:
            self.dlg.AuxPath.setText(file_path)

    def select_output_file(self):
        """Opens a file dialog to select or create the output file
           (GeoPackage)."""
        file_path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            "Select output file",
            "",
            "GeoPackage (*.gpkg);;All Files (*)"
        )
        if file_path:
            self.dlg.OutputPath.setText(file_path)

    def select_workspace_file(self):
        """Opens a dialog to select a workspace folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self.dlg,
            "Select workspace folder",
            ""
        )
        if folder_path:
            self.dlg.WorkspacePath.setText(folder_path)

    def select_filter_file(self):
        """Opens a file dialog to select the filter file
        and processes it."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,  # Dialog is part of the GUI
            "Select filter config file",
            "",
            "Text files (*.txt);;All Files (*)"
        )
        if file_path:
            self.dlg.FilterPath.setText(file_path)
            self.load_filter_file(file_path)

    def select_log_dir(self):
        """Open a directory dialog to select the log output directory."""
        folder_path = QFileDialog.getExistingDirectory(
            self.dlg,
            "Select log directory",
            ""
        )
        if folder_path:
            self.dlg.LogDirPath.setText(folder_path)

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------

    def _go_prev_step(self):
        """Navigate to the previous step."""
        idx = self.dlg.stackedWidget.currentIndex()
        self.dlg.set_step(max(0, idx - 1))

    def _go_next_step(self):
        """Navigate to the next step."""
        idx = self.dlg.stackedWidget.currentIndex()
        self.dlg.set_step(min(3, idx + 1))

    # ------------------------------------------------------------------
    # Inline path validation
    # ------------------------------------------------------------------

    def _check_path_field(self, field_name: str, path: str) -> None:
        """Quick path-existence check triggered by textChanged.

        Does not load any QGIS layer — pure filesystem check.
        """
        if not path:
            self.dlg.set_field_status(field_name, None)
            return

        is_ok, message = InputValidator().quick_path_check(path)
        self.dlg.set_field_status(field_name, is_ok, message if not is_ok else "")

        # Enable showFilterButton only when FilterPath is a valid file
        if field_name == 'FilterPath':
            self.dlg.showFilterButton.setEnabled(is_ok)

    # ------------------------------------------------------------------
    # Log utilities
    # ------------------------------------------------------------------

    def _copy_log_to_clipboard(self):
        """Copy the MessageBox content to the system clipboard."""
        text = self.dlg.MessageBox.toPlainText()
        QApplication.clipboard().setText(text)

    # ------------------------------------------------------------------
    # Result actions (shown after successful processing)
    # ------------------------------------------------------------------

    def _load_result_to_qgis(self):
        """Load the last output GeoPackage as a layer in QGIS."""
        if not self._last_output_path or not os.path.exists(self._last_output_path):
            msg("Output file not found.")
            return
        layer = QgsVectorLayer(self._last_output_path, "IB-Tool result", "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            msg(f"Could not load result layer: {self._last_output_path}")

    def _open_output_dir(self):
        """Open the output directory in the file explorer."""
        folder = self._last_output_folder or os.path.dirname(self._last_output_path)
        if folder and os.path.isdir(folder):
            os.startfile(folder)
        else:
            msg("Output directory not found.")

    def _export_log(self):
        """Save the current log content to a text file."""
        text = self.dlg.MessageBox.toPlainText()
        if not text:
            msg("No log content to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            "Export log",
            self._last_output_folder or "",
            "Text files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                logger.log(f"Log exported to: {file_path}", level="INFO")
            except Exception as e:
                msg(f"Could not export log: {e}")

    def _show_filter_preview(self):
        """Open the FilterPreviewDialog with the current filter content."""
        positive = self.dlg.txtPositive.toPlainText()
        negative = self.dlg.txtNegative.toPlainText()
        dlg = FilterPreviewDialog(positive, negative, parent=self.dlg)
        dlg.exec_()

    def load_filter_file(self, file_path):
        """Read a filter file and populate the positive/negative filter text fields.

        Args:
            file_path: Absolute path to the filter ``.txt`` file. Expected
                format: sections delimited by ``#Filter positive`` and
                ``#Filter negative`` comment lines.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            # Extract filters
            positive_filters = []
            negative_filters = []
            current_section = None

            for line in lines:
                line = line.strip()
                if line.startswith("#Filter positive"):
                    current_section = "positive"
                elif line.startswith("#Filter negative"):
                    current_section = "negative"
                elif line.startswith("#") or not line:
                    continue
                else:
                    if current_section == "positive":
                        positive_filters.append(line)
                    elif current_section == "negative":
                        negative_filters.append(line)

            # Display the filters in the GUI (e.g., text fields in your dialog)
            self.dlg.txtPositive.setPlainText("\n".join(positive_filters))
            self.dlg.txtNegative.setPlainText("\n".join(negative_filters))

            # logger.log("Filter file successfully loaded.", level="INFO")

        except Exception as e:
            logger.log(f"Error while loading the filter file: {str(e)}",
                       level="CRITICAL")

    def _apply_config_to_ui(self) -> None:
        """Populate all UI fields from CONFIG.ini if it exists and auto_load_last_used is True."""
        if not self.config_manager.config_exists():
            return
        cfg = self.config_manager.get_config()
        if not cfg.ui.auto_load_last_used:
            return

        # Pfad-Felder befüllen
        self.config_manager.apply_to_ui_elements({
            'HuPath': self.dlg.HuPath,
            'RnPath': self.dlg.RnPath,
            'PartPath': self.dlg.PartPath,
            'AuxPath': self.dlg.AuxPath,
            'FilterPath': self.dlg.FilterPath,
            'WorkspacePath': self.dlg.WorkspacePath,
            'OutputPath': self.dlg.OutputPath,
            'LogDirPath': self.dlg.LogDirPath,
        })

        # CRS
        if cfg.processing.crs_epsg:
            self.dlg.SpatialReferenceBox.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{cfg.processing.crs_epsg}"))

        # Log-Level
        valid_levels = ['INFO', 'WARNING', 'CRITICAL', 'SUCCESS']
        if cfg.ui.log_level in valid_levels:
            self.dlg.LogLevelBox.setCurrentText(cfg.ui.log_level)

        # Partitions-Parameter
        if cfg.processing.part_start > 0:
            self.dlg.partstartBox.setText(str(cfg.processing.part_start))
        if cfg.processing.part_end > 0:
            self.dlg.partendBox.setText(str(cfg.processing.part_end))
        if cfg.processing.part_list:
            self.dlg.partlistBox.setText(cfg.processing.part_list)

        # Settlement-Analyse-Parameter (QSpinBox — nur wenn > 0)
        proc = cfg.processing
        if proc.min_building_count > 0:
            self.dlg.MinBdgCountBox.setValue(int(proc.min_building_count))
        if proc.min_overlap_blocks > 0:
            self.dlg.MinOverlapBlocksBox.setValue(int(proc.min_overlap_blocks))
        if proc.global_footprint_density > 0:
            self.dlg.GlobalFootprintDensityBox.setValue(int(proc.global_footprint_density))
        if proc.min_area > 0:
            self.dlg.MinAreaBox.setValue(int(proc.min_area))
        if proc.min_patch_size > 0:
            self.dlg.MinPatchSizeBox.setValue(int(proc.min_patch_size))
        if proc.max_hole_size > 0:
            self.dlg.MaxHoleSizeBox.setValue(int(proc.max_hole_size))
        if proc.max_gap_size > 0:
            self.dlg.MaxGapSizeBox.setValue(int(proc.max_gap_size))

        # Checkboxen
        self.dlg.DebugModeBox.setChecked(cfg.processing.debug_mode)
        self.dlg.PartLogBox.setChecked(cfg.processing.delete_part_log)

        # Filter-Datei laden, wenn gesetzt
        filter_path = cfg.input_data.filter_file_path
        if filter_path and os.path.exists(filter_path):
            self.load_filter_file(filter_path)

        logger.log("Konfiguration aus CONFIG.ini geladen.", level="INFO")

    def _save_config_from_ui(self) -> None:
        """Persist the current UI state to CONFIG.ini."""
        self.config_manager.update_config(
            input_data={
                'building_footprints_path': self.dlg.HuPath.text(),
                'road_network_path': self.dlg.RnPath.text(),
                'partitions_path': self.dlg.PartPath.text(),
                'aux_layer_path': self.dlg.AuxPath.text(),
                'filter_file_path': self.dlg.FilterPath.text(),
            },
            output={
                'workspace_directory': self.dlg.WorkspacePath.text(),
                'output_directory': self.dlg.OutputPath.text(),
            },
            ui={
                'log_level': self.dlg.LogLevelBox.currentText(),
                'log_directory': self.dlg.LogDirPath.text(),
            },
            processing={
                'min_overlap_blocks': float(self.dlg.MinOverlapBlocksBox.value()),
                'global_footprint_density': float(self.dlg.GlobalFootprintDensityBox.value()),
                'min_area': float(self.dlg.MinAreaBox.value()),
                'min_building_count': int(self.dlg.MinBdgCountBox.value()),
                'min_patch_size': float(self.dlg.MinPatchSizeBox.value()),
                'max_hole_size': float(self.dlg.MaxHoleSizeBox.value()),
                'max_gap_size': float(self.dlg.MaxGapSizeBox.value()),
                'part_start': int(self.dlg.partstartBox.text() or -1),
                'part_end': int(self.dlg.partendBox.text() or -1),
                'part_list': self.dlg.partlistBox.text(),
                'crs_epsg': int(self.dlg.SpatialReferenceBox.crs().authid().split(":")[-1].strip() or 25832),
                'debug_mode': self.dlg.DebugModeBox.isChecked(),
                'delete_part_log': self.dlg.PartLogBox.isChecked(),
            },
        )
        self.config_manager.save_config()
        logger.log("Konfiguration in CONFIG.ini gespeichert.", level="INFO")

    def _collect_params(self) -> dict:
        """Collect all UI parameter values as raw strings for validation.

        Returns:
            Dict mapping parameter names to their current widget text values.
            All numeric values are returned as strings; the caller is
            responsible for conversion and validation.
        """
        return {
            "min_overlap_blocks": self.dlg.MinOverlapBlocksBox.text(),
            "global_footprint_density": self.dlg.GlobalFootprintDensityBox.text(),
            "min_area": self.dlg.MinAreaBox.text(),
            "min_bdg_count": self.dlg.MinBdgCountBox.text(),
            "min_patch_size": self.dlg.MinPatchSizeBox.text(),
            "max_hole_size": self.dlg.MaxHoleSizeBox.text(),
            "max_gap_size": self.dlg.MaxGapSizeBox.text(),
            "spatial_reference_text": self.dlg.SpatialReferenceBox.crs().authid(),
            "part_start": self.dlg.partstartBox.text(),
            "part_end": self.dlg.partendBox.text(),
            "part_list": self.dlg.partlistBox.text(),
        }

    @staticmethod
    def _parse_float(text: str, fallback: float) -> float:
        """Parse a UI widget string to float, using fallback on failure.

        Args:
            text: Raw string value from a QLineEdit or QSpinBox widget.
            fallback: Value returned when ``text`` cannot be converted.

        Returns:
            Parsed float value, or ``fallback`` if conversion fails.
        """
        try:
            return float(text)
        except ValueError:
            logger.log(
                f"Invalid numeric value: {text!r} — using fallback {fallback}.",
                level="WARNING",
            )
            return fallback

    def _parse_numeric_params(self) -> dict:
        """Read and parse all numeric processing parameters from the UI.

        Uses :meth:`_parse_float` to convert widget text to numbers, logging a
        WARNING and substituting the fallback value when conversion fails.

        Returns:
            Dict with keys ``min_overlap_blocks``, ``global_footprint_density``,
            ``min_area``, ``min_bdg_count``, ``min_patch_size``,
            ``max_hole_size``, ``max_gap_size``, ``part_start``, ``part_end``.
        """
        return {
            'min_overlap_blocks': self._parse_float(
                self.dlg.MinOverlapBlocksBox.text(), 0.0),
            'global_footprint_density': self._parse_float(
                self.dlg.GlobalFootprintDensityBox.text(), 0.0),
            'min_area': self._parse_float(self.dlg.MinAreaBox.text(), 0.0),
            'min_bdg_count': int(self._parse_float(self.dlg.MinBdgCountBox.text(), 0)),
            'min_patch_size': self._parse_float(self.dlg.MinPatchSizeBox.text(), 0.0),
            'max_hole_size': self._parse_float(self.dlg.MaxHoleSizeBox.text(), 0.0),
            'max_gap_size': self._parse_float(self.dlg.MaxGapSizeBox.text(), 0.0),
            'part_start': (
                int(self._parse_float(self.dlg.partstartBox.text(), -1))
                if self.dlg.partstartBox.text() else -1
            ),
            'part_end': (
                int(self._parse_float(self.dlg.partendBox.text(), -1))
                if self.dlg.partendBox.text() else -1
            ),
        }

    def run_validation(self):
        """Run input validation and display results in MessageBox."""
        self.dlg.MessageBox.clear()

        spatial_reference = self.dlg.SpatialReferenceBox.crs()

        validator = InputValidator()
        result = validator.validate_all(
            hu_path=self.dlg.HuPath.text(),
            rn_path=self.dlg.RnPath.text(),
            part_path=self.dlg.PartPath.text(),
            aux_path=self.dlg.AuxPath.text(),
            filter_path=self.dlg.FilterPath.text(),
            output_path=self.dlg.OutputPath.text(),
            workspace_path=self.dlg.WorkspacePath.text(),
            spatial_reference=spatial_reference,
            params=self._collect_params(),
        )

        self._display_validation_result(result)
        self.dlg.set_start_button_ready(result.is_valid)

    def _display_validation_result(self, result: ValidationResult) -> None:
        """Format and display validation results in MessageBox and checklist."""
        # Always populate the visual checklist
        self.dlg.populate_validation_checklist(result.errors, result.warnings)

        if result.is_valid and not result.warnings:
            logger.log(
                "=== VALIDATION SUCCESSFUL === "
                "All input data checks passed.",
                level="INFO"
            )
        else:
            if result.errors:
                logger.log(
                    f"=== VALIDATION ERRORS ({len(result.errors)}) ===",
                    level="CRITICAL"
                )
                for i, error in enumerate(result.errors, 1):
                    logger.log(f"  [{i}] {error}", level="CRITICAL")

            if result.warnings:
                logger.log(
                    f"=== WARNINGS ({len(result.warnings)}) ===",
                    level="WARNING"
                )
                for i, warning in enumerate(result.warnings, 1):
                    logger.log(f"  [{i}] {warning}", level="WARNING")

            if result.is_valid:
                logger.log(
                    "Validation passed (with warnings). "
                    "Processing can be started.",
                    level="INFO"
                )
            else:
                logger.log(
                    "Validation failed. "
                    "Please fix errors above before starting.",
                    level="CRITICAL"
                )

        # Navigate to step 2 (Validierung) so the checklist is visible
        self.dlg.set_step(2)

    def start_processing(self):
        """Run the full settlement-delineation pipeline for all partitions.

        Reads all parameter values from the UI, re-validates input, loads
        layers into GeoPackage format, then iterates over the partition list.
        For each partition the pipeline runs six sequential steps:
        Load → Blocker → ImportFilter → MST → Clustering → GapClose →
        PatchRemove. Intermediate results are accumulated in a merge layer
        and saved to disk after each partition to enable resume. On
        completion the result is saved to the configured output GeoPackage
        and the result-action buttons are shown.

        Processing runs synchronously on the main thread (not in
        ``ProcessingThread``). ``QApplication.processEvents()`` is called
        after each phase-progress update to keep the UI responsive.
        """

        # Navigate to the processing page and reset UX state
        self.dlg.set_step(3)
        self.dlg.hide_result_actions()
        self.dlg.phaseLabel.setText("Starting processing...")
        self.dlg.ProgressBar.setValue(0)
        QApplication.processEvents()

        # Ensure logger uses the level selected in the GUI
        selected_level = self.dlg.LogLevelBox.currentText()
        if selected_level:
            try:
                logger.set_log_level(selected_level)
            except ValueError as e:
                msg(str(e))

        log_dir = self.dlg.LogDirPath.text()
        if log_dir:
            logger.set_log_dir(log_dir)

        workspace = os.getcwd()
        os.chdir(workspace)

        _p = self._parse_numeric_params()
        min_overlap_blocks = _p['min_overlap_blocks']
        global_footprint_density = _p['global_footprint_density']
        min_area = _p['min_area']
        min_bdg_count = _p['min_bdg_count']
        min_patch_size = _p['min_patch_size']
        max_hole_size = _p['max_hole_size']
        max_gap_size = _p['max_gap_size']
        part_start = _p['part_start']
        part_end = _p['part_end']

        part_list_input = self.dlg.partlistBox.text()

        del_part_log = self.dlg.PartLogBox.isChecked()
        msg(f"del_part_log={del_part_log}")
        debug_mode = self.dlg.DebugModeBox.isChecked()
        spatial_reference = self.dlg.SpatialReferenceBox.crs()
        logger.log(f"spatial_reference: {spatial_reference.authid()}", 'INFO')

        if part_list_input[0] != "#":
            part_list_input = list(part_list_input.split(","))

        workspace_path = self.dlg.WorkspacePath.text() + "/"
        msg(f"workspace_path={workspace_path}")
        manage_directory(workspace_path, del_part_log)

        part_log_path = workspace_path + 'IB_Tool_Results/IB_Tool2_Log.txt'
        part_log_fin = workspace_path + 'IB_Tool_Results/IB_Tool2_Log_Fin.txt'

        # Pfade zu den Eingabe-Shapefiles
        input_hu = self.dlg.HuPath.text()
        input_rn = self.dlg.RnPath.text()
        input_aux = self.dlg.AuxPath.text()
        input_part = self.dlg.PartPath.text()
        input_filter = self.dlg.FilterPath.text()
        output_file = self.dlg.OutputPath.text()

        # Input validation (replaces old check_projection call)
        validator = InputValidator()
        validation_result = validator.validate_all(
            hu_path=input_hu,
            rn_path=input_rn,
            part_path=input_part,
            aux_path=input_aux,
            filter_path=input_filter,
            output_path=output_file,
            workspace_path=self.dlg.WorkspacePath.text(),
            spatial_reference=spatial_reference,
            params=self._collect_params(),
        )
        self._display_validation_result(validation_result)
        if not validation_result.is_valid:
            logger.log("Verarbeitung abgebrochen wegen Validierungsfehlern.",
                       level="CRITICAL")
            return

        # Phase 1: Load Data
        self.dlg.set_phase_progress(1, 6, "Load Data", 0)
        QApplication.processEvents()

        # Alle Eingabe-Shapefiles in das GeoPackage laden
        layer_rn = load_to_geopackage(input_rn,
                                      workspace_path + "layer_rn.gpkg",
                                      "layer_rn", spatial_reference)
        layer_rn.dataProvider().createSpatialIndex()
        layer_aux = load_to_geopackage(input_aux,
                                       workspace_path + "layer_aux.gpkg",
                                       "layer_aux", spatial_reference)
        layer_aux.dataProvider().createSpatialIndex()
        layer_part = load_to_geopackage(input_part,
                                        workspace_path + "layer_part.gpkg",
                                        "layer_part", spatial_reference)
        layer_part.dataProvider().createSpatialIndex()
        layer_hu = load_to_geopackage(input_hu,
                                      workspace_path + "layer_hu.gpkg",
                                      "layer_hu", spatial_reference)
        layer_hu.dataProvider().createSpatialIndex()

        aux_layers_line = processing.run("qgis:mergevectorlayers", {
            'LAYERS': [layer_aux, layer_rn],
            'CRS': spatial_reference,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        })['OUTPUT']

        merge_temp_file = workspace_path + 'IB_Tool_Results/IB_Tool_merge_temp.gpkg'
        if not del_part_log and os.path.isfile(merge_temp_file):
            merge_layer = QgsVectorLayer(merge_temp_file, 'global_merge_layer', 'ogr')
            if not merge_layer.isValid():
                logger.log("Intermediate merge file invalid, starting fresh", 'WARNING')
                merge_layer = create_empty_layer("global_merge_layer", "Polygon",
                                                 spatial_reference.authid())
            else:
                logger.log("Loaded intermediate merge layer for resume", 'INFO')
        else:
            merge_layer = create_empty_layer("global_merge_layer", "Polygon",
                                             spatial_reference.authid())
        merge = merge_layer  # Initialize to avoid UnboundLocalError if loop doesn't execute
        # Partitionen aus Gesamtdatei für Debugging auswählen
        part_list = create_partitions_list(layer_part,  # noqa: F405
                                           part_list_input,
                                           part_start,
                                           part_end)

        logger.log(f"Part list: {part_list}", 'SUCCESS')

        # calculate threshold value for footprint density
        if global_footprint_density == 0:
            global_footprint_density = calc_footprint_density(
                layer_hu,
                layer_rn,
                100,
                0,
                'global',
                min_bdg_count,
                layer_part)
        else:
            pass

        logger.log(f"Global building coverage threshold = {global_footprint_density}", "CRITICAL")

        if del_part_log:
            if os.path.isfile(part_log_path):
                os.remove(part_log_path)

            with open(part_log_fin, 'w', encoding='utf-8') as part_log:
                part_log.write("")

        if not os.path.isfile(part_log_path):
            with open(part_log_path, 'w', encoding='utf-8') as part_log:
                part_log.write("")

        if not os.path.isfile(part_log_fin):
            with open(part_log_fin, 'w', encoding='utf-8') as f:
                f.write("")

        finished_parts = set()
        with open(part_log_fin, 'r', encoding='utf-8') as f:
            finished_parts = {row.strip() for row in f if row.strip()}

        anz_hu_gesamt = layer_hu.featureCount()
        anz_hu_sum = 0

        for a, i in enumerate(part_list, start=1):
            logger.log(f"Check if {i} is in Partlist.", 'SUCCESS')
            if i in finished_parts:
                logger.log(f"{i} already completed, skipping.", 'SUCCESS')
                continue
            with open(part_log_path, 'a', encoding='utf-8') as part_log:
                part_log.write("\n" + i)

            part_name = i
            logger.log("###############################", 'CRITICAL')
            logger.log("PARTITION: " + str(part_name) + " - " + str(a) + " of "
                       + str(len(part_list)), 'CRITICAL')

            # Partition auswählen
            sel_part_layer = processing.run(
                "native:extractbyexpression", {
                    'INPUT': layer_part,
                    'EXPRESSION': f"\"NAME\" = '{part_name}'",
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                })['OUTPUT']

            # Gebäude-Features selektieren
            sel_hu_layer = select_and_save_by_location(layer_hu, sel_part_layer)

            # Anzahl der ausgewählten Gebäude prüfen
            anz_hu = sel_hu_layer.featureCount()

            if anz_hu < 10:
                with open(part_log_fin, 'a', encoding='utf-8') as part_log:
                    part_log.write("\n" + part_name)
                logger.log("Warning: No or less than 10 buildings selected in partition", 'WARNING')
                continue

            # Straßen-Features selektieren
            sel_strassen_layer = select_and_save_by_location(layer_rn, sel_part_layer)

            # Anzahl der ausgewählten Straßen prüfen
            anz_strassen = sel_strassen_layer.featureCount()

            if anz_strassen < 5:
                with open(part_log_fin, 'a', encoding='utf-8') as part_log:
                    part_log.write("\n" + part_name)
                logger.log(f"Warning: No or less than 5 roads selected in partition {part_name}", 'WARNING')

            aux_lines_sel = select_and_save_by_location(aux_layers_line, sel_part_layer)

            # Debug-Ausgaben
            logger.log(f"SelHU Count = {anz_hu}", 'SUCCESS')
            logger.log(f"SelStrassen Count = {anz_strassen}", 'SUCCESS')

            min_overlap_mst = calc_footprint_density(sel_hu_layer, sel_strassen_layer, 100, global_footprint_density, 'local',  # noqa: E501
                                                     min_bdg_count)

            logger.log("Local building coverage =" + str(min_overlap_mst), 'SUCCESS')

            # Phase 2: Calculate Blocks
            self.dlg.set_phase_progress(2, 6, "Calculate Blocks", 10)
            QApplication.processEvents()

            blocks = blocker(aux_lines_sel, sel_hu_layer, sel_part_layer,
                             debug_mode=debug_mode, workspace_path=workspace_path)

            # Phase 3: Apply Filter
            self.dlg.set_phase_progress(3, 6, "Apply Filter", 20)
            QApplication.processEvents()

            hu_filter = input_hu_filter(sel_hu_layer, input_filter, min_area, 50, 200,
                                        debug_mode=debug_mode, workspace_path=workspace_path)

            blocks_dense = identify_dense_blocks(hu_filter, blocks, min_overlap_blocks)

            hu_filter_sel = select_and_save_by_location(hu_filter, blocks_dense, [2], 0)

            # Phase 4: Calculate MST
            self.dlg.set_phase_progress(4, 6, "Calculate MST", 40)
            QApplication.processEvents()

            mst_layer = calculate_mst(hu_filter_sel, sel_strassen_layer, spatial_reference)

            # Check if MST calculation succeeded
            if mst_layer is None:
                with open(part_log_fin, 'a', encoding='utf-8') as part_log:
                    part_log.write("\n" + part_name)
                logger.log(f"MST calculation failed for partition {part_name}, skipping", 'WARNING')
                continue

            # Phase 5: Clustering
            self.dlg.set_phase_progress(5, 6, "Clustering", 60)
            QApplication.processEvents()

            hu_cluster_output = mst_clustering(hu_filter_sel, mst_layer, spatial_reference, min_overlap_mst,
                                               debug_mode=debug_mode, workspace_path=workspace_path)

            add_sing_bdg = add_single_bdg(hu_filter_sel, hu_cluster_output, spatial_reference,
                                          workspace_path, debug_mode=debug_mode)

            rect_merged = processing.run("qgis:mergevectorlayers", {
                'LAYERS': [add_sing_bdg, hu_cluster_output],
                'CRS': spatial_reference,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            snapped_rect = edge_catch(rect_merged, hu_filter_sel,
                                      sel_strassen_layer, blocks,
                                      spatial_reference, workspace_path,
                                      debug_mode=debug_mode)

            blocks_merge = processing.run("qgis:mergevectorlayers", {
                'LAYERS': [snapped_rect, blocks_dense],
                'CRS': spatial_reference,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']

            gaps_colsed = gap_close(blocks_merge, blocks, max_hole_size, max_gap_size, spatial_reference, gap_dist=30,
                                    debug_mode=debug_mode, workspace_path=workspace_path)

            patch_removed = patch_remove(gaps_colsed,
                                         sel_hu_layer,
                                         spatial_reference,
                                         workspace_path,
                                         min_patch_size=min_patch_size,
                                         min_bdg_count=min_bdg_count,
                                         footprint_area_sum=6000,
                                         footprint_density_threshold=18,
                                         debug_mode=debug_mode)

            # Fortschritt aktualisieren
            anz_hu_sum = anz_hu_sum + anz_hu
            prozent = int(anz_hu_sum / anz_hu_gesamt * 100)
            self.dlg.ProgressBar.setValue(prozent)

            merge = processing.run("native:mergevectorlayers", {
                'LAYERS': [patch_removed, merge_layer],
                'CRS': spatial_reference,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            })['OUTPUT']
            merge_layer = merge

            # Zwischenergebnis auf Disk sichern (für Resume)
            save_temp_layer_to_gpkg(
                merge_layer,
                'IB_Tool_merge_temp',
                workspace_path + 'IB_Tool_Results/'
            )
            # Partition als abgeschlossen markieren
            with open(part_log_fin, 'a', encoding='utf-8') as part_log:
                part_log.write("\n" + part_name)
            finished_parts.add(part_name)

        # Load output from previous step
        if not merge.isValid():
            logger.log("Failed to load final merge layer", "CRITICAL")
            return

        # gap_fixed = gap_fix(merge, layer_rn, workspace_path, debug_mode=debug_mode)

        # Phase 6: Save Output
        self.dlg.set_phase_progress(6, 6, "Save Output", 95)
        QApplication.processEvents()

        # Split the output_file into path, filename, and extension
        output_folder, file_with_extension = os.path.split(output_file)
        output_filename, _ = os.path.splitext(file_with_extension)
        msg(output_folder)
        msg(output_filename)

        save_temp_layer_to_gpkg(merge_layer, str(output_filename), output_folder + "/")

        # Processing complete
        self.dlg.ProgressBar.setValue(100)
        self.dlg.phaseLabel.setText("Processing complete")
        self._last_output_path = output_file
        self._last_output_folder = output_folder
        self.dlg.show_result_actions()

        logger.log("Processing completed successfully.", level="CRITICAL")
