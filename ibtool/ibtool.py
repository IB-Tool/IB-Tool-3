# -*- coding: utf-8 -*-
# pylint: disable=too-many-lines
"""Main plugin class and processing orchestrator for IBTool.

This module contains the ``IBTool`` QGIS plugin class, which owns the plugin
lifecycle (``initGui`` / ``unload``), the 4-step stepper UI dialog, all file-
dialog helpers, input validation, configuration persistence (CONFIG.ini), and
the ``start_processing()`` method that drives the full settlement-delineation
pipeline partition by partition.

Classes:
    IBTool: Main QGIS plugin class registered via ``classFactory()``.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""

import json
import os
from contextlib import ExitStack
import subprocess
import sys

from qgis.PyQt.QtCore import (
    QCoreApplication,
    QEventLoop,
    QSettings,
    QTranslator,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QFileDialog,
    QApplication,
    QMessageBox,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsVectorLayer,
    QgsProject,
)
from qgis import processing
from ibtool.helpers.processing_context import (
    current_processing_context,
    shared_processing_context,
    ui_heartbeat,
)
from ibtool.helpers.logger import Logger as MainLogger
from ibtool.helpers.geometry_utils import (
    load_to_geopackage,
    create_empty_layer
)
from ibtool.helpers.system_utils import (
    manage_directory,
    save_temp_layer_to_gpkg,
    version_check,
    compute_file_checksum,
    get_user_config_dir,
    migrate_legacy_config,
)
from ibtool.helpers.message import msg
from ibtool.helpers.check import InputValidator, ValidationResult
from ibtool.helpers.config_manager import ConfigManager
from ibtool.helpers.data_loader import create_partitions_list
from ibtool.ibtool_tools.FootprintDensity import calc_footprint_density
from ibtool.helpers.partition_pipeline import run_partition, PHASE_PERCENT
from ibtool.helpers.partition_results import (
    FinishedPart,
    OLD_FORMAT,
    append_finished,
    cleanup_temporary,
    estimate_buildings,
    merge_order,
    merge_results,
    plan_partitions,
    read_finished,
    validate_finished,
    write_part_result,
)
from ibtool.helpers.run_manifest import (
    build_manifest,
    compare_manifests,
    manifest_to_ui_settings,
    read_manifest,
    write_manifest,
)
from ibtool.helpers.worker_launcher import default_worker_count, find_worker_command
from ibtool.helpers.worker_pool import WorkerPool
# Import the dialog class
from ibtool.ibtool.ibtool_dialog import IBToolDialog, FilterPreviewDialog
# Logger class (singleton handled internally; no early file init on import)
logger = MainLogger


def _open_directory(path: str) -> None:
    """Open a directory in the system file explorer, cross-platform.

    Args:
        path: Absolute path to the directory to open.
    """
    if sys.platform == "win32":
        os.startfile(path)  # nosec B606 — path validated by caller
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # nosec B603, B607
    else:
        try:
            subprocess.Popen(["xdg-open", path])  # nosec B603, B607
        except FileNotFoundError:
            msg("Cannot open folder: xdg-open not found on this system.")


class ProcessingCancelledError(BaseException):
    """Raised inside start_processing() when the user requests cancellation.

    Derives from ``BaseException`` (like ``KeyboardInterrupt``): it is raised
    from the UI heartbeat *inside* tools, many of which catch ``Exception``
    broadly (e.g. ``safe_processing_run`` would treat it as a failed algorithm).
    """


class IBTool:  # pylint: disable=too-many-instance-attributes
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
        # Plugin root is one level above ibtool/ibtool/
        plugin_root = os.path.dirname(self.plugin_dir)
        # CONFIG.ini and logs live in the QGIS profile so plugin updates
        # (which replace the plugin folder) do not wipe them.
        try:
            self.config_dir = get_user_config_dir()
            migrate_legacy_config(plugin_root, self.config_dir)
        except OSError as exc:
            logger.log(
                f"Profile config dir unavailable ({exc}); using plugin folder.",
                level="WARNING")
            self.config_dir = plugin_root
        self.config_manager = ConfigManager(self.config_dir)
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            plugin_root,
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

        # Last successful output paths (used by result action buttons)
        self._last_output_path = ""
        self._last_output_folder = ""

        # Processing state flags for cancel support
        self._is_processing: bool = False
        self._cancel_requested: bool = False
        # Worker pool while partitions are computed in worker processes
        self._pool = None

        # Overall progress bookkeeping (buildings done / current partition / total)
        self._progress_total_hu: int = 0
        self._progress_done_hu: int = 0
        self._progress_part_hu: int = 0
        self._last_percent: int = 0

        # Checksum cache: field_name → MD5 hex of file at last path-check
        self._file_checksums: dict = {}
        # Checksum snapshot at the time of the last completed validation run
        self._validated_checksums: dict = {}
        # Full validation context snapshot (paths, checksums, CRS, params)
        self._validated_context: dict = {}
        # Cached ValidationResult from the last run (None = never validated)
        self._last_validation_result = None
        # Per-file content-check cache (InputValidator.validate_all's
        # `previous_cache`/`layer_cache`), keyed by field name. Deliberately
        # NOT cleared by _invalidate_validation_cache: it lets run_validation
        # skip re-scanning files that have not changed even when an
        # unrelated setting (e.g. CRS, a parameter) forces a fresh check.
        self._validation_layer_cache: dict = {}

    def update_progress(self, value):
        """Update progress bar"""
        self.dlg.ProgressBar.setValue(value)

    def update_messages(self, message):
        """Display messages in the window"""
        self.dlg.MessageBox.appendPlainText(message)

    def cancel_processing(self):
        """Close the dialog when idle; request abort between phases when processing."""
        if not self._is_processing:
            self.dlg.close()
        else:
            self._cancel_requested = True
            self.update_messages("Abbruch wird nach dem aktuellen Schritt durchgeführt...")
            if self._pool is not None:          # worker mode: stop the workers at once
                self._pool.cancel()

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

    def add_action(  # pylint: disable=too-many-arguments
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
        if self._pool is not None:              # never leave worker processes behind
            self._cancel_requested = True
            self._pool.cancel()
        for action in self.actions:
            self.iface.removePluginMenu(
                self.menu,
                action)
            self.iface.removeToolBarIcon(action)

        # Close the logger
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
            # Typed-in working directory: offer the settings of a begun run
            self.dlg.WorkspacePath.editingFinished.connect(
                lambda: self._offer_manifest_restore(self.dlg.WorkspacePath.text()))
            self.dlg.FilterButton.clicked.connect(self.select_filter_file)
            self.dlg.LogDirButton.clicked.connect(self.select_log_dir)
            self.dlg.CheckButton.clicked.connect(self.run_validation)
            self.dlg.StartButton.clicked.connect(self.start_processing)
            self.dlg.CancelButton.clicked.connect(self.cancel_processing)
            self.dlg.SaveConfigButton.clicked.connect(self._save_config_from_ui)
            self.dlg.DeleteConfigButton.clicked.connect(self._delete_config)
            # Start button disabled by default — requires successful check
            self.dlg.set_start_button_ready(False)
            # Any validation-relevant UI change invalidates the cached result.
            for path_widget in [
                self.dlg.HuPath,
                self.dlg.RnPath,
                self.dlg.PartPath,
                self.dlg.AuxPath,
                self.dlg.FilterPath,
                self.dlg.OutputPath,
                self.dlg.WorkspacePath,
            ]:
                path_widget.textChanged.connect(self._invalidate_validation_cache)
            for param_widget in [
                self.dlg.MinOverlapBlocksBox,
                self.dlg.GlobalFootprintDensityBox,
                self.dlg.MinAreaBox,
                self.dlg.MinBdgCountBox,
                self.dlg.MinPatchSizeBox,
                self.dlg.MaxHoleSizeBox,
                self.dlg.MaxGapSizeBox,
            ]:
                param_widget.valueChanged.connect(self._invalidate_validation_cache)
            for part_widget in [
                self.dlg.partstartBox,
                self.dlg.partendBox,
                self.dlg.partlistBox,
            ]:
                part_widget.textChanged.connect(self._invalidate_validation_cache)
            self.dlg.SpatialReferenceBox.crsChanged.connect(
                self._invalidate_validation_cache
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
            self.dlg.SpatialReferenceBox.setCrs(QgsCoordinateReferenceSystem("EPSG:25833"))

        # Load config from CONFIG.ini into the UI
        self._apply_config_to_ui()

        # Refresh the text fields automatically on start
        file_path = self.dlg.FilterPath.text()  # Read the path from the QLineEdit
        if file_path and os.path.exists(file_path):  # Check whether the path exists
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
            self.tr("Select building footprints file"),
            "",
            self.tr("Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*)")
        )
        if file_path:
            self.dlg.HuPath.setText(file_path)  # Display the path in QLineEdit

    def select_rn_file(self):
        """Opens a file dialog to select the RN file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            self.tr("Select road network file"),
            "",
            self.tr("Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*)")
        )
        if file_path:
            self.dlg.RnPath.setText(file_path)  # Display the path in QLineEdit

    def select_part_file(self):
        """Opens a file dialog to select the PART file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            self.tr("Select partitions file"),
            "",
            self.tr("Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*)")
        )
        if file_path:
            self.dlg.PartPath.setText(
                file_path)  # Display the path in QLineEdit

    def select_aux_file(self):
        """Opens a file dialog to select the AUX file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            self.tr("Select auxiliary data file"),
            "",
            self.tr("Vector files (*.shp *.gpkg);;Shapefiles (*.shp);;GeoPackage (*.gpkg);;All Files (*)")
        )
        if file_path:
            self.dlg.AuxPath.setText(file_path)

    def select_output_file(self):
        """Opens a file dialog to select or create the output file
           (GeoPackage)."""
        file_path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            self.tr("Select output file"),
            "",
            self.tr("GeoPackage (*.gpkg);;All Files (*)")
        )
        if file_path:
            self.dlg.OutputPath.setText(file_path)

    def select_workspace_file(self):
        """Opens a dialog to select a workspace folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self.dlg,
            self.tr("Select workspace folder"),
            ""
        )
        if folder_path:
            self.dlg.WorkspacePath.setText(folder_path)
            self._offer_manifest_restore(folder_path)

    # Manifest parameter key -> UI spin box (see _parse_numeric_params)
    _MANIFEST_PARAM_BOXES = {
        "min_overlap_blocks": "MinOverlapBlocksBox",
        "global_footprint_density": "GlobalFootprintDensityBox",
        "min_area": "MinAreaBox",
        "min_bdg_count": "MinBdgCountBox",
        "min_patch_size": "MinPatchSizeBox",
        "max_hole_size": "MaxHoleSizeBox",
        "max_gap_size": "MaxGapSizeBox",
    }
    # Manifest input key -> UI path field
    _MANIFEST_INPUT_FIELDS = {"hu": "HuPath", "rn": "RnPath", "part": "PartPath",
                              "aux": "AuxPath", "filter": "FilterPath"}

    def _offer_manifest_restore(self, workspace: str) -> None:
        """Offer the settings of a begun run in *workspace* (``ibtool_run.json``).

        Asks only if the manifest's inputs, parameters or CRS differ from the
        dialog; on "Yes" the dialog fields are set from the manifest.
        """
        if not workspace:
            return
        manifest = read_manifest(workspace)
        if manifest is None:
            return
        settings = manifest_to_ui_settings(manifest)
        changes = {}
        for key, path in settings["inputs"].items():
            field = self._MANIFEST_INPUT_FIELDS.get(key)
            if field and path and getattr(self.dlg, field).text() != path:
                changes[field] = path
        for key, value in settings["params"].items():
            box_name = self._MANIFEST_PARAM_BOXES.get(key)
            if box_name and value is not None:
                box = getattr(self.dlg, box_name)
                current = box.value()
                value_type = type(current)
                if current != value_type(value):
                    changes[box_name] = value
        crs = settings.get("crs")
        if crs and self.dlg.SpatialReferenceBox.crs().authid() != crs:
            changes["crs"] = crs
        if not changes:
            return
        answer = QMessageBox.question(
            self.dlg, "IB-Tool",
            self.tr("This working directory contains a run that has already been started.\n"
                    "Take over its settings (input data and parameters)?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return
        for name, value in changes.items():
            if name == "crs":
                self.dlg.SpatialReferenceBox.setCrs(QgsCoordinateReferenceSystem(value))
            elif name in self._MANIFEST_INPUT_FIELDS.values():
                getattr(self.dlg, name).setText(value)
            else:
                box = getattr(self.dlg, name)
                box.setValue(type(box.value())(value))
        if "FilterPath" in changes and os.path.exists(changes["FilterPath"]):
            self.load_filter_file(changes["FilterPath"])
        logger.log("Einstellungen aus dem Laufprotokoll übernommen.", "INFO")

    def select_filter_file(self):
        """Opens a file dialog to select the filter file
        and processes it."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,  # Dialog is part of the GUI
            self.tr("Select filter config file"),
            "",
            self.tr("Text files (*.txt);;All Files (*)")
        )
        if file_path:
            self.dlg.FilterPath.setText(file_path)
            self.load_filter_file(file_path)

    def select_log_dir(self):
        """Open a directory dialog to select the log output directory."""
        folder_path = QFileDialog.getExistingDirectory(
            self.dlg,
            self.tr("Select log directory"),
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

    # Fields for which a checksum is computed (input files, not directories).
    _CHECKSUM_FIELDS = frozenset({'HuPath', 'RnPath', 'PartPath', 'AuxPath', 'FilterPath'})
    _VALIDATION_PATH_FIELDS = (
        'HuPath', 'RnPath', 'PartPath', 'AuxPath',
        'FilterPath', 'OutputPath', 'WorkspacePath',
    )

    def _invalidate_validation_cache(self, *_args) -> None:
        """Clear cached validation state after a relevant UI change."""
        self._last_validation_result = None
        self._validated_checksums.clear()
        self._validated_context = {}
        self.dlg.set_start_button_ready(False)

    def _build_validation_context(self) -> dict:
        """Capture the current validation-relevant UI state."""
        return {
            'paths': {
                field_name: getattr(self.dlg, field_name).text()
                for field_name in self._VALIDATION_PATH_FIELDS
            },
            'checksums': {
                field_name: self._file_checksums.get(field_name, '')
                for field_name in self._CHECKSUM_FIELDS
            },
            'params': self._collect_params(),
        }

    def _can_reuse_validation_result(self) -> bool:
        """Return True when the cached validation result still matches the UI."""
        if self._last_validation_result is None:
            return False

        if not all(self._file_checksums.get(field) for field in self._CHECKSUM_FIELDS):
            return False

        return self._validated_context == self._build_validation_context()

    def _check_path_field(self, field_name: str, path: str) -> None:
        """Quick path-existence check triggered by textChanged.

        Does not load any QGIS layer — pure filesystem check.
        For input file fields the MD5 checksum of the file is stored in
        ``self._file_checksums`` so that :meth:`run_validation` can skip
        re-validation when files have not changed.
        """
        if not path:
            self.dlg.set_field_status(field_name, None)
            self._file_checksums.pop(field_name, None)
            return

        is_ok, message = InputValidator().quick_path_check(path)
        self.dlg.set_field_status(field_name, is_ok, message if not is_ok else "")

        # Compute and cache checksum for input file fields
        if field_name in self._CHECKSUM_FIELDS:
            if is_ok and os.path.isfile(path):
                self._file_checksums[field_name] = compute_file_checksum(path)
            else:
                self._file_checksums.pop(field_name, None)

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
            msg(self.tr("Output file not found."))
            return
        layer = QgsVectorLayer(self._last_output_path, self.tr("IB-Tool result"), "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            msg(f"Could not load result layer: {self._last_output_path}")

    def _open_output_dir(self):
        """Open the output directory in the file explorer."""
        folder = self._last_output_folder or os.path.dirname(self._last_output_path)
        if folder and os.path.isdir(folder):
            _open_directory(folder)
        else:
            msg(self.tr("Output directory not found."))

    def _export_log(self):
        """Save the current log content to a text file."""
        text = self.dlg.MessageBox.toPlainText()
        if not text:
            msg(self.tr("No log content to export."))
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            self.tr("Export log"),
            self._last_output_folder or "",
            self.tr("Text files (*.txt);;All Files (*)")
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                logger.log(f"Log exported to: {file_path}", level="INFO")
            except OSError as e:
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

        except (OSError, UnicodeDecodeError) as e:
            logger.log(f"Error while loading the filter file: {str(e)}",
                       level="CRITICAL")

    def _apply_config_to_ui(self) -> None:  # pylint: disable=too-many-branches,too-many-statements
        """Populate all UI fields from CONFIG.ini if it exists and auto_load_last_used is True."""
        if not self.config_manager.config_exists():
            return
        cfg = self.config_manager.get_config()
        if not cfg.ui.auto_load_last_used:
            return

        # Fill the path fields
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

        # Settlement analysis parameters (QSpinBox - only if > 0)
        proc = cfg.processing
        if proc.min_building_count > 0:
            self.dlg.MinBdgCountBox.setValue(int(proc.min_building_count))
        if proc.min_overlap_blocks > 0:
            self.dlg.MinOverlapBlocksBox.setValue(int(proc.min_overlap_blocks))
        if proc.global_footprint_density > 0:
            self.dlg.GlobalFootprintDensityBox.setValue(proc.global_footprint_density)
        if proc.min_area > 0:
            self.dlg.MinAreaBox.setValue(int(proc.min_area))
        if proc.min_patch_size > 0:
            self.dlg.MinPatchSizeBox.setValue(int(proc.min_patch_size))
        if proc.max_hole_size > 0:
            self.dlg.MaxHoleSizeBox.setValue(int(proc.max_hole_size))
        if proc.max_gap_size > 0:
            self.dlg.MaxGapSizeBox.setValue(int(proc.max_gap_size))

        # Checkboxes
        self.dlg.DebugModeBox.setChecked(cfg.processing.debug_mode)
        self.dlg.PartLogBox.setChecked(cfg.processing.delete_part_log)
        self.dlg.WorkerCountBox.setValue(int(cfg.processing.worker_count))

        # Load the filter file if set
        filter_path = cfg.input_data.filter_file_path
        if filter_path and os.path.exists(filter_path):
            self.load_filter_file(filter_path)

        # Restore validated-checksums snapshot so run_validation can skip
        # re-validation when the files haven't changed since last session.
        inp = cfg.input_data
        self._validated_checksums = {
            'HuPath': inp.building_footprints_checksum,
            'RnPath': inp.road_network_checksum,
            'PartPath': inp.partitions_checksum,
            'AuxPath': inp.aux_layer_checksum,
            'FilterPath': inp.filter_file_checksum,
        }

        # Restore cached ValidationResult from last session
        try:
            validation_cache = cfg.validation_cache
            cached_errors = json.loads(validation_cache.errors) if validation_cache.errors else []
            cached_warnings = json.loads(validation_cache.warnings) if validation_cache.warnings else []
            cached_context = (
                json.loads(validation_cache.context_signature)
                if getattr(validation_cache, 'context_signature', '')
                else {}
            )
            if cached_errors is not None or cached_warnings:
                restored = ValidationResult()
                restored.errors = cached_errors
                restored.warnings = cached_warnings
                self._last_validation_result = restored
            self._validated_context = cached_context if isinstance(cached_context, dict) else {}
        except (json.JSONDecodeError, AttributeError, TypeError):
            self._last_validation_result = None
            self._validated_context = {}

        logger.log(self.tr("Configuration loaded from CONFIG.ini."), level="INFO")

    def _save_config_from_ui(self) -> None:
        """Persist the current UI state to CONFIG.ini."""
        self.config_manager.update_config(
            input_data={
                'building_footprints_path': self.dlg.HuPath.text(),
                'road_network_path': self.dlg.RnPath.text(),
                'partitions_path': self.dlg.PartPath.text(),
                'aux_layer_path': self.dlg.AuxPath.text(),
                'filter_file_path': self.dlg.FilterPath.text(),
                # Persist last-known checksums for cross-session skip logic
                'building_footprints_checksum': self._file_checksums.get('HuPath', ''),
                'road_network_checksum': self._file_checksums.get('RnPath', ''),
                'partitions_checksum': self._file_checksums.get('PartPath', ''),
                'aux_layer_checksum': self._file_checksums.get('AuxPath', ''),
                'filter_file_checksum': self._file_checksums.get('FilterPath', ''),
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
                'crs_epsg': int(self.dlg.SpatialReferenceBox.crs().authid().split(":")[-1].strip() or 25833),
                'debug_mode': self.dlg.DebugModeBox.isChecked(),
                'delete_part_log': self.dlg.PartLogBox.isChecked(),
                'worker_count': int(self.dlg.WorkerCountBox.value()),
            },
        )
        validation_cache = {
            'errors': '[]',
            'warnings': '[]',
            'context_signature': '',
        }
        if self._last_validation_result is not None:
            validation_cache = {
                'errors': json.dumps(self._last_validation_result.errors),
                'warnings': json.dumps(self._last_validation_result.warnings),
                'context_signature': json.dumps(self._validated_context),
            }
        self.config_manager.update_config(validation_cache=validation_cache)

        self.config_manager.save_config()
        logger.log(self.tr("Configuration saved to CONFIG.ini."), level="INFO")

    def _delete_config(self) -> None:
        """Delete CONFIG.ini and reset all UI fields to factory defaults.

        Asks the user for confirmation before deleting. After deletion the
        ConfigManager is re-initialised with an empty default configuration
        and all path / parameter fields in the UI are cleared.
        """
        reply = QMessageBox.question(
            self.dlg,
            self.tr("Reset Configuration"),
            self.tr("Delete CONFIG.ini and reset all fields to defaults?\n"
                    "This action cannot be undone."),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Delete the file if it exists
        cfg_path = self.config_manager.config_file_path
        if os.path.exists(cfg_path):
            try:
                os.remove(cfg_path)
            except OSError as e:
                logger.log(f"Fehler beim Löschen der CONFIG.ini: {e}", level="CRITICAL")
                return

        # Re-init manager with empty defaults
        self.config_manager = ConfigManager(self.config_dir)

        # Clear all path fields
        for widget in [
            self.dlg.HuPath, self.dlg.RnPath, self.dlg.PartPath,
            self.dlg.AuxPath, self.dlg.FilterPath,
            self.dlg.OutputPath, self.dlg.WorkspacePath, self.dlg.LogDirPath,
        ]:
            widget.clear()

        # Clear filter preview text fields
        self.dlg.txtPositive.clear()
        self.dlg.txtNegative.clear()

        # Reset parameter spinboxes and line edits to UI defaults
        self.dlg.MinOverlapBlocksBox.setValue(18)
        self.dlg.GlobalFootprintDensityBox.setValue(0)
        self.dlg.MinAreaBox.setValue(57)
        self.dlg.MinBdgCountBox.setValue(20)
        self.dlg.MinPatchSizeBox.setValue(10000)
        self.dlg.MaxHoleSizeBox.setValue(10000)
        self.dlg.MaxGapSizeBox.setValue(4900)
        self.dlg.partstartBox.setText("-1")
        self.dlg.partendBox.setText("-1")
        self.dlg.partlistBox.setText("#")
        self.dlg.DebugModeBox.setChecked(False)
        self.dlg.PartLogBox.setChecked(True)
        self.dlg.WorkerCountBox.setValue(0)
        self.dlg.SpatialReferenceBox.setCrs(QgsCoordinateReferenceSystem("EPSG:25833"))

        # Reset checksum and validation caches
        self._file_checksums.clear()
        self._validated_checksums.clear()
        self._validated_context = {}
        self._last_validation_result = None
        self._validation_layer_cache.clear()

        # Disable Start button (re-check required)
        self.dlg.set_start_button_ready(False)

        logger.log(self.tr("Configuration reset — CONFIG.ini deleted."), level="INFO")

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
        """Run input validation and display results in MessageBox.

        Skips the full QGIS-layer validation when all input-file checksums
        match those stored from the previous run and a cached
        ``ValidationResult`` is available. This avoids redundant layer loads
        when the user clicks *Check* multiple times without changing files.
        """
        self.dlg.MessageBox.clear()

        # ------------------------------------------------------------------
        # Validation skip: re-use the cached result only when the current
        # inputs and validation-relevant parameters still match exactly.
        # ------------------------------------------------------------------
        if self._can_reuse_validation_result():
            logger.log(
                self.tr("Validation skipped — inputs and parameters unchanged."),
                level="INFO",
            )
            self._display_validation_result(self._last_validation_result)
            self.dlg.set_start_button_ready(self._last_validation_result.is_valid)
            return

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
            file_checksums=self._file_checksums,
            previous_cache=self._validation_layer_cache,
        )

        # Store result and snapshot checksums for next skip-check
        self._last_validation_result = result
        self._validated_checksums = dict(self._file_checksums)
        self._validated_context = self._build_validation_context()
        # Per-file content-check cache for files unchanged in the next run,
        # even if this run itself was not a full-context cache hit.
        self._validation_layer_cache = result.layer_cache

        self._display_validation_result(result)
        self.dlg.set_start_button_ready(result.is_valid)

    def _display_validation_result(self, result: ValidationResult,
                                   show_page: bool = True) -> None:
        """Format and display validation results in MessageBox and checklist.

        Args:
            result: Validation result to display.
            show_page: Switch to the validation page (step 2). ``start_processing``
                passes ``False`` for a successful re-validation so the progress
                page stays visible.
        """
        # Always populate the visual checklist
        self.dlg.populate_validation_checklist(result.errors, result.warnings)

        if result.is_valid and not result.warnings:
            logger.log(
                self.tr("=== VALIDATION SUCCESSFUL === All input data checks passed."),
                level="INFO"
            )
        else:
            if result.errors:
                logger.log(
                    self.tr("=== VALIDATION ERRORS ({count}) ===").format(
                        count=len(result.errors)),
                    level="CRITICAL"
                )
                for i, error in enumerate(result.errors, 1):
                    logger.log(f"  [{i}] {error}", level="CRITICAL")

            if result.warnings:
                logger.log(
                    self.tr("=== WARNINGS ({count}) ===").format(count=len(result.warnings)),
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
        if show_page:
            self.dlg.set_step(2)

    # Share of the progress bar for the partition loop (rest: Save Output)
    _PARTITION_PROGRESS_SPAN = 95

    # Controls disabled while processing runs (Cancel stays enabled)
    _PROCESSING_LOCKED_WIDGETS = (
        "StartButton", "CheckButton", "backButton", "nextButton",
        "stepBtn0", "stepBtn1", "stepBtn2", "stepBtn3", "DeleteConfigButton",
    )

    def _overall_percent(self, partition_percent: int) -> int:
        """Convert a progress value within the current partition to overall progress.

        Overall progress = (buildings of finished partitions + share of the
        current partition) / all buildings, scaled to ``_PARTITION_PROGRESS_SPAN``.
        The value never decreases. Without totals (pipeline called outside
        ``start_processing()``) *partition_percent* is returned unchanged.

        Args:
            partition_percent: Progress within the current partition (0–100).

        Returns:
            Overall progress in percent (0–100).
        """
        if not self._progress_total_hu:
            return partition_percent
        done = self._progress_done_hu + self._progress_part_hu * partition_percent / 100
        percent = int(self._PARTITION_PROGRESS_SPAN * min(done / self._progress_total_hu, 1.0))
        self._last_percent = max(self._last_percent, percent)
        return self._last_percent

    def _keep_ui_alive(self) -> None:
        """UI heartbeat during processing: process events and honour Cancel.

        Called via ``ui_heartbeat`` before every ``processing.run()`` (at most
        every 0.2 s), so the window does not freeze during long tools.

        Raises:
            ProcessingCancelledError: If the user requested cancellation.
        """
        QApplication.processEvents()
        if self._cancel_requested:
            raise ProcessingCancelledError()

    def _set_processing_ui_locked(self, locked: bool) -> None:
        """Disable (or re-enable) controls that must not be used while processing.

        While events are processed during a run, a click on Start would
        otherwise launch a nested run; navigation would leave the progress page.
        """
        for name in self._PROCESSING_LOCKED_WIDGETS:
            widget = getattr(self.dlg, name, None)
            if widget is not None:
                widget.setEnabled(not locked)

    def _update_phase(self, phase: int, total: int, name: str, percent: int) -> None:
        """Update the phase progress indicator and flush pending UI events.

        ``name`` is the English phase name; it is translated here (context
        ``IBTool``), so the entries in ``i18n/IBTool_de.ts`` are maintained by hand.
        """
        self.dlg.set_phase_progress(phase, total, self.tr(name), percent)
        QApplication.processEvents()
        if self._cancel_requested:
            raise ProcessingCancelledError()

    def _load_input_layers(self, input_hu, input_rn, input_aux, input_part,  # pylint: disable=too-many-arguments
                           workspace_path, spatial_reference):
        """Load all input files into GeoPackage and build the merged aux line layer.

        Args:
            input_hu: Path to the building footprint layer.
            input_rn: Path to the road network layer.
            input_aux: Path to the auxiliary lines layer.
            input_part: Path to the partition layer.
            workspace_path: Workspace directory path (trailing slash).
            spatial_reference: Target CRS for all layers.

        Returns:
            Tuple of ``(layer_hu, layer_rn, layer_aux, layer_part, aux_layers_line)``.
        """
        layer_rn = load_to_geopackage(
            input_rn, workspace_path + "layer_rn.gpkg", "layer_rn", spatial_reference)
        layer_rn.dataProvider().createSpatialIndex()
        layer_aux = load_to_geopackage(
            input_aux, workspace_path + "layer_aux.gpkg", "layer_aux", spatial_reference)
        layer_aux.dataProvider().createSpatialIndex()
        layer_part = load_to_geopackage(
            input_part, workspace_path + "layer_part.gpkg", "layer_part", spatial_reference)
        layer_part.dataProvider().createSpatialIndex()
        layer_hu = load_to_geopackage(
            input_hu, workspace_path + "layer_hu.gpkg", "layer_hu", spatial_reference)
        layer_hu.dataProvider().createSpatialIndex()
        aux_layers_line = processing.run("qgis:mergevectorlayers", {
            'LAYERS': [layer_aux, layer_rn],
            'CRS': spatial_reference,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }, context=current_processing_context())['OUTPUT']
        return layer_hu, layer_rn, layer_aux, layer_part, aux_layers_line

    def _run_partition_pipeline(  # pylint: disable=too-many-arguments
            self, part_name, part_index, part_count,
            layers, spatial_reference, workspace_path,
            debug_mode, global_footprint_density, params):
        """Run one partition in this process (sequential path / recompute list).

        Thin wrapper around :func:`ibtool.helpers.partition_pipeline.run_partition`
        (the only partition pipeline implementation) that adds the partition
        banner and the dialog progress updates.

        Returns:
            Tuple ``(result_layer, building_count)``; *result_layer* is ``None``
            if the partition is skipped.
        """
        logger.log("###############################", 'CRITICAL')
        logger.log(
            f"PARTITION: {part_name} - {part_index} of {part_count}", 'CRITICAL')

        def _progress(phase, phase_name):
            self._update_phase(phase, 9, phase_name,
                               self._overall_percent(PHASE_PERCENT[phase]))

        def _selected(count):
            self._progress_part_hu = count

        return run_partition(part_name, layers, spatial_reference, workspace_path,
                             debug_mode, global_footprint_density, params,
                             progress=_progress, on_selected=_selected)

    # -- Phase 4: worker mode, part files, run manifest -------------------------

    def _effective_worker_count(self) -> int:
        """Worker processes to use: the UI value, or automatic if it is 0 / absent."""
        box = getattr(self.dlg, "WorkerCountBox", None)
        value = box.value() if box is not None else 0
        return value if value > 0 else default_worker_count()

    def _plugin_version(self) -> str:
        """Plugin version from metadata.txt (empty if unreadable)."""
        path = os.path.join(os.path.dirname(self.plugin_dir), "metadata.txt")
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("version="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return ""

    def _prepare_manifest(self, workspace, inputs, params, crs, del_part_log) -> bool:
        """Check the run manifest of *workspace* and mark the run as ``running``.

        A resume (``del_part_log`` off) is refused with a message box if the
        stored manifest differs from the current inputs/parameters/versions.

        Returns:
            ``False`` if processing must not start.
        """
        current = build_manifest(inputs, params, crs, self._plugin_version(), Qgis.version(),
                                 self._effective_worker_count())
        if not del_part_log:
            stored = read_manifest(workspace)
            if stored is None:
                log_fin = workspace + 'IB_Tool_Results/IB_Tool2_Log_Fin.txt'
                if read_finished(log_fin):
                    logger.log("Kein Laufprotokoll (ibtool_run.json) gefunden – älterer Lauf, "
                               "Fortsetzung ohne Prüfung der Eingabedaten.", "WARNING")
            else:
                diffs = compare_manifests(stored, current)
                if diffs:
                    text = ("Das Arbeitsverzeichnis enthält einen Lauf mit anderen "
                            "Einstellungen und kann nicht fortgesetzt werden:\n\n"
                            + "\n".join(f"• {d}" for d in diffs)
                            + "\n\nFür einen Neustart „PartLog beim Start löschen“ aktivieren "
                              "oder ein anderes Arbeitsverzeichnis wählen.")
                    logger.log(text, "CRITICAL")
                    QMessageBox.warning(self.dlg, "IB-Tool", text)
                    return False
        write_manifest(workspace, current, "running")
        return True

    @staticmethod
    def _set_manifest_status(workspace, status) -> None:
        """Update the status of the run manifest (ignored if there is none)."""
        stored = read_manifest(workspace)
        if stored is not None:
            try:
                write_manifest(workspace, stored, status)
            except OSError as e:
                logger.log(f"Laufprotokoll nicht aktualisiert: {e}", "WARNING")

    @staticmethod
    def _resume_base_layer(results_dir, finished, spatial_reference):
        """Base layer of the final merge.

        Results of partitions finished by a version before 0.2.5 live only in
        ``IB_Tool_merge_temp.gpkg``; it becomes the base layer then. Otherwise
        (and if that file is unusable) an empty layer is used.
        """
        if any(part.result == OLD_FORMAT for part in finished.values()):
            merge_temp = os.path.join(results_dir, 'IB_Tool_merge_temp.gpkg')
            layer = QgsVectorLayer(merge_temp, 'global_merge_layer', 'ogr') \
                if os.path.isfile(merge_temp) else None
            if layer is not None and layer.isValid():
                logger.log("Zwischenergebnis eines älteren Laufs übernommen "
                           "(IB_Tool_merge_temp.gpkg).", 'INFO')
                return layer
            logger.log("IB_Tool_merge_temp.gpkg fehlt oder ist ungültig – Ergebnisse der mit "
                       "einer älteren Version berechneten Partitionen fehlen. Für ein "
                       "vollständiges Ergebnis „PartLog beim Start löschen“ aktivieren.",
                       'CRITICAL')
        return create_empty_layer("global_merge_layer", "Polygon", spatial_reference.authid())

    @staticmethod
    def _largest_first(names, estimates) -> list:
        """*names* sorted by estimated size, largest first (stable for ties)."""
        return sorted(names, key=lambda name: -estimates.get(name, 0))

    def _on_partition_finished(self, name, rel_path, features, buildings, log_fin) -> None:
        """Record a finished partition (finish line) and advance the progress bar.

        The part file (if any) is already written; only then the finish line
        is appended, so a resume never trusts an incomplete file.
        """
        append_finished(log_fin, FinishedPart(name, rel_path, features if rel_path else None))
        self._progress_done_hu += buildings
        self.dlg.ProgressBar.setValue(self._overall_percent(0))

    def _dispatch_partitions(self, names, ctx, worker_count) -> None:
        """Compute *names* in worker processes if possible, else in this process.

        Worker mode needs more than one worker and partition, a worker command
        for this system and a passing self-test; otherwise (and for
        partitions whose worker crashed or failed) the sequential path runs.
        """
        command = None
        if worker_count > 1 and len(names) > 1:
            command = find_worker_command(os.path.dirname(self.plugin_dir))
            if command is None:
                logger.log("Worker-Modus auf diesem System nicht verfügbar – "
                           "Partitionen werden nacheinander berechnet.", "INFO")
        if command is None:
            self._process_partitions_sequential(names, ctx)
            return

        pool = WorkerPool(command, min(worker_count, len(names)), ctx["init_fields"])
        self._pool = pool
        try:
            self.dlg.phaseLabel.setText(self.tr("Starting workers..."))
            if not pool.selftest():
                if self._cancel_requested:
                    raise ProcessingCancelledError()
                logger.log("Worker-Selbsttest fehlgeschlagen – Partitionen werden "
                           "nacheinander berechnet.", "WARNING")
                for line in pool.stderr_tail(20):
                    logger.log(f"  {line}", "INFO")
                self._pool = None
                self._process_partitions_sequential(names, ctx)
                return
            recompute = self._process_partitions_parallel(names, ctx, pool)
        finally:
            self._pool = None
        if recompute:
            logger.log(f"Im Hauptprozess nachzurechnen: {', '.join(recompute)}", "WARNING")
            self._process_partitions_sequential(recompute, ctx)

    def _process_partitions_sequential(self, names, ctx) -> None:
        """Compute *names* one after another in this process."""
        part_list = ctx["part_list"]
        for name in names:
            with open(ctx["part_log"], 'a', encoding='utf-8') as part_log:
                part_log.write("\n" + name)
            self._progress_part_hu = 0
            # One shared processing context per partition (fresh per partition
            # to release layers QGIS keeps in the context's temporary store)
            with shared_processing_context():
                result, buildings = self._run_partition_pipeline(
                    name, part_list.index(name) + 1, len(part_list), ctx["layers"], ctx["crs"],
                    ctx["workspace"], ctx["debug_mode"], ctx["global_density"], ctx["params"])
                rel_path, features = (None, 0) if result is None else \
                    write_part_result(result, name, ctx["results_dir"])
            self._progress_part_hu = 0
            self._on_partition_finished(name, rel_path, features,
                                        ctx["estimates"].get(name, buildings), ctx["log_fin"])

    def _process_partitions_parallel(self, names, ctx, pool) -> list:
        """Compute *names* with *pool* (largest first); return the recompute list.

        The QGIS main thread runs a local event loop until the pool is
        finished, so the dialog stays responsive; Cancel stops the pool.

        Raises:
            ProcessingCancelledError: If the user cancelled.
        """
        estimates = ctx["estimates"]
        order = self._largest_first(names, estimates)
        partial, started, done = {}, set(), []
        workers = min(pool.size, len(order))

        def _status():
            running = ", ".join(sorted(pool.running.values()))
            text = self.tr("{workers} workers · {done} of {total} partitions finished").format(
                workers=workers, done=len(done), total=len(order))
            if running:
                text += self.tr(" · running: {names}").format(names=running)
            self.dlg.phaseLabel.setText(text)

        def _on_progress(partition, phase, _phase_name):
            if partition not in started:
                started.add(partition)
                with open(ctx["part_log"], 'a', encoding='utf-8') as part_log:
                    part_log.write("\n" + partition)
            partial[partition] = estimates.get(partition, 0) * PHASE_PERCENT.get(phase, 0) / 100
            self._progress_part_hu = sum(partial.values())
            self.dlg.ProgressBar.setValue(self._overall_percent(100))
            _status()

        def _on_log(level, message):
            logger.log(message, level if level in ("INFO", "WARNING", "CRITICAL", "SUCCESS")
                       else "WARNING")

        def _on_done(event):
            name = event["partition"]
            partial.pop(name, None)
            self._progress_part_hu = sum(partial.values())
            self._on_partition_finished(name, event["result"], event["features"],
                                        estimates.get(name, event["buildings"]), ctx["log_fin"])
            done.append(name)
            logger.log(f"Partition {name} fertig ({event['seconds']:.1f} s)", "SUCCESS")
            _status()

        pool.progress.connect(_on_progress)
        pool.log.connect(_on_log)
        pool.partition_done.connect(_on_done)
        finished = []
        loop = QEventLoop()
        pool.finished.connect(lambda: finished.append(True))
        pool.finished.connect(loop.quit)
        _status()
        pool.run(order)
        if not finished:
            loop.exec_()
        self._progress_part_hu = 0
        if self._cancel_requested:
            raise ProcessingCancelledError()
        failed = set(pool.recompute)
        return [name for name in names if name in failed]

    def _effective_log_dir(self) -> str:
        """Return the log directory from the UI, or ``<config_dir>/logs`` if empty."""
        return self.dlg.LogDirPath.text().strip() or os.path.join(self.config_dir, "logs")

    def start_processing(
            self):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """Run the full settlement-delineation pipeline for all partitions.

        Reads all parameter values from the UI, re-validates input, loads
        layers into GeoPackage format, then iterates over the partition list.
        Progress is reported in nine phases: Load Data, then per partition
        Calculate Blocks, Apply Filter, Calculate MST, Clustering, Erode
        Empty Areas, Close Gaps, Remove Patches, and finally Save Output.
        Intermediate results are accumulated in a merge layer
        and saved to disk after each partition to enable resume. On
        completion the result is saved to the configured output GeoPackage
        and the result-action buttons are shown.

        Processing runs synchronously on the main thread. A UI heartbeat
        (``ui_heartbeat`` → ``_keep_ui_alive``) processes UI events before
        every ``processing.run()`` (at most every 0.2 s) and honours Cancel;
        Start, Check and the navigation are disabled while it runs. The
        progress bar shows overall progress (buildings processed / total).
        """
        if self._is_processing:
            # Re-entrant click on Start while events are processed during a run
            return
        self._cancel_requested = False
        self._is_processing = True
        self._progress_total_hu = 0
        self._progress_done_hu = 0
        self._progress_part_hu = 0
        self._last_percent = 0
        ui_stack = ExitStack()
        manifest_workspace = None
        try:
            self._set_processing_ui_locked(True)
            # Navigate to the processing page and reset UX state
            self.dlg.set_step(3)
            self.dlg.hide_result_actions()
            self.dlg.phaseLabel.setText(self.tr("Starting processing..."))
            self.dlg.ProgressBar.setValue(0)
            QApplication.processEvents()

            # Ensure logger uses the level selected in the GUI
            selected_level = self.dlg.LogLevelBox.currentText()
            if selected_level:
                try:
                    logger.set_log_level(selected_level)
                except ValueError as e:
                    msg(str(e))

            logger.set_log_dir(self._effective_log_dir())

            workspace = os.getcwd()
            os.chdir(workspace)

            _p = self._parse_numeric_params()
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

            input_hu = self.dlg.HuPath.text()
            input_rn = self.dlg.RnPath.text()
            input_aux = self.dlg.AuxPath.text()
            input_part = self.dlg.PartPath.text()
            output_file = self.dlg.OutputPath.text()
            _p['input_filter'] = self.dlg.FilterPath.text()

            # Input validation
            validator = InputValidator()
            validation_result = validator.validate_all(
                hu_path=input_hu,
                rn_path=input_rn,
                part_path=input_part,
                aux_path=input_aux,
                filter_path=_p['input_filter'],
                output_path=output_file,
                workspace_path=self.dlg.WorkspacePath.text(),
                spatial_reference=spatial_reference,
                params=self._collect_params(),
            )
            # Stay on the progress page unless the re-validation found errors
            self._display_validation_result(
                validation_result, show_page=not validation_result.is_valid)
            if not validation_result.is_valid:
                logger.log(self.tr("Processing aborted due to validation errors."),
                           level="CRITICAL")
                return

            # Keep the UI responsive (and Cancel effective) during all tools
            ui_stack.enter_context(ui_heartbeat(self._keep_ui_alive))

            # Run manifest: one working directory = one run. Checked before the
            # (slow) loading so a refused resume costs nothing.
            manifest_inputs = {"hu": input_hu, "rn": input_rn, "part": input_part,
                               "aux": input_aux, "filter": _p['input_filter']}
            manifest_params = {key: value for key, value in _p.items()
                               if key not in ("part_start", "part_end", "input_filter")}
            if not self._prepare_manifest(workspace_path, manifest_inputs, manifest_params,
                                          spatial_reference.authid(), del_part_log):
                self.dlg.phaseLabel.setText(self.tr("Cannot resume — see message."))
                return
            manifest_workspace = workspace_path

            # Phase 1: Load Data
            self._update_phase(1, 9, "Load Data", 0)
            with shared_processing_context():
                layer_hu, layer_rn, _, layer_part, aux_layers_line = self._load_input_layers(
                    input_hu, input_rn, input_aux, input_part, workspace_path, spatial_reference)
            # Workers and the sequential path read the very same aux line file
            aux_line_file = save_temp_layer_to_gpkg(
                aux_layers_line, "layer_aux_line", workspace_path)
            aux_layers_line = QgsVectorLayer(aux_line_file or "", "aux_layers_line", "ogr")
            if not aux_layers_line.isValid():
                raise OSError(f"Hilfslinien-Layer nicht lesbar: {aux_line_file}")

            part_list = [str(name) for name in create_partitions_list(
                layer_part, part_list_input, _p['part_start'], _p['part_end'])]
            logger.log(f"Part list: {part_list}", 'SUCCESS')

            global_footprint_density = _p['global_footprint_density']
            if global_footprint_density == 0:
                with shared_processing_context():
                    global_footprint_density = calc_footprint_density(
                        layer_hu, layer_rn, 100, 0, 'global', _p['min_bdg_count'], layer_part)
            logger.log(
                f"Global building coverage threshold = {global_footprint_density}", "CRITICAL")

            results_dir = workspace_path + 'IB_Tool_Results'
            for path in (part_log_path, part_log_fin):
                if not os.path.isfile(path):
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write("")
            cleanup_temporary(results_dir)

            # Resume: trust a finished partition only if its part file is complete
            valid, recompute = validate_finished(results_dir, read_finished(part_log_fin))
            for name in recompute:
                logger.log(f"Teilergebnis von {name} fehlt oder ist unvollständig – "
                           "wird neu berechnet.", "WARNING")
            # work_list = selection + invalid results of earlier batches
            work_list, todo = plan_partitions(part_list, valid, recompute)
            if len(todo) < len(work_list):
                logger.log(f"{len(work_list) - len(todo)} Partition(en) bereits fertig – "
                           "werden übersprungen.", "INFO")

            # Progress = estimated buildings of finished partitions / of all
            estimates = estimate_buildings(layer_hu, layer_part, work_list)
            self._progress_total_hu = max(1, sum(estimates.values()))
            self._progress_done_hu = sum(estimates[name] for name in work_list
                                         if name in valid)
            self.dlg.ProgressBar.setValue(self._overall_percent(0))

            ctx = {
                "part_list": work_list,
                "layers": {
                    'layer_part': layer_part,
                    'layer_hu': layer_hu,
                    'layer_rn': layer_rn,
                    'aux_layers_line': aux_layers_line,
                },
                "crs": spatial_reference,
                "workspace": workspace_path,
                "results_dir": results_dir,
                "log_fin": part_log_fin,
                "part_log": part_log_path,
                "params": _p,
                "debug_mode": debug_mode,
                "global_density": global_footprint_density,
                "estimates": estimates,
                "init_fields": {
                    "plugin_root": os.path.dirname(self.plugin_dir),
                    "sys_path": list(sys.path),
                    "prefix_path": QgsApplication.prefixPath(),
                    "inputs": {"hu": workspace_path + "layer_hu.gpkg",
                               "rn": workspace_path + "layer_rn.gpkg",
                               "part": workspace_path + "layer_part.gpkg",
                               "aux_line": aux_line_file},
                    "crs": spatial_reference.authid(),
                    "params": _p,
                    "workspace": workspace_path,
                    "results_dir": results_dir,
                    "debug_mode": debug_mode,
                    "global_density": global_footprint_density,
                    "log_level": self.dlg.LogLevelBox.currentText() or "INFO",
                    "parent_pid": os.getpid(),
                },
            }
            if todo:
                self._dispatch_partitions(todo, ctx, self._effective_worker_count())

            # Final merge: earlier batches (resume with another selection) first,
            # then the selected partitions in list order — the order of the
            # former incremental merge, independent of the worker count.
            finished = read_finished(part_log_fin)
            order = merge_order(finished, part_list)
            merge_layer = merge_results(
                results_dir, order, finished,
                self._resume_base_layer(results_dir, finished, spatial_reference),
                spatial_reference)

            if not merge_layer.isValid():
                logger.log("Failed to load final merge layer", "CRITICAL")
                return

            # Phase 9: Save Output
            self._update_phase(9, 9, "Save Output", 95)
            output_folder, file_with_extension = os.path.split(output_file)
            output_filename, _ = os.path.splitext(file_with_extension)
            msg(output_folder)
            msg(output_filename)

            save_temp_layer_to_gpkg(merge_layer, str(output_filename), output_folder + "/")

            self.dlg.ProgressBar.setValue(100)
            self.dlg.phaseLabel.setText(self.tr("Processing complete"))
            self._last_output_path = output_file
            self._last_output_folder = output_folder
            self.dlg.show_result_actions()

            self._set_manifest_status(manifest_workspace, "finished")
            logger.log("Processing completed successfully.", level="CRITICAL")
        except ProcessingCancelledError:
            if manifest_workspace:
                self._set_manifest_status(manifest_workspace, "cancelled")
            self.dlg.phaseLabel.setText(self.tr("Processing cancelled."))
            self.update_messages(self.tr("Processing cancelled."))
            logger.log("Verarbeitung durch Nutzer abgebrochen.", level="WARNING")
        except Exception:
            if manifest_workspace:
                self._set_manifest_status(manifest_workspace, "failed")
            raise
        finally:
            if self._pool is not None:          # never leave worker processes behind
                self._pool.cancel()
                self._pool = None
            ui_stack.close()
            self._set_processing_ui_locked(False)
            self._is_processing = False
            self._cancel_requested = False
