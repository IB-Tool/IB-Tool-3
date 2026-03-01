import os
import tempfile
import pytest
from unittest.mock import patch, Mock

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)

# Nutze die zentrale QGIS-Initialisierung aus test/__init__.py
from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class DummyLogger:
    logs = []

    @classmethod
    def log(cls, message, level=None):
        cls.logs.append((message, level))


class TestManageDirectory:
    EXPECTED_DIRECTORY_NAME = 'IB_Tool_Results'

    def setup_method(self, method):
        self.tmp = tempfile.TemporaryDirectory()
        self._setup_manage_directory_function()
        self._setup_logger_mock()

    def _setup_manage_directory_function(self):
        """Importiert und setzt die manage_directory Funktion."""
        from ibtool.helpers.system_utils import manage_directory
        self.manage_directory = manage_directory

    def _setup_logger_mock(self):
        """Richtet das Logger-Mocking ein."""
        from ibtool.helpers import system_utils
        self.patcher = patch.object(system_utils, 'Logger', DummyLogger)
        self.patcher.start()

    def _create_test_workspace(self):
        """Erstellt einen Test-Workspace und gibt den Pfad zurück."""
        workspace_path = os.path.join(self.tmp.name, 'ws')
        os.makedirs(workspace_path)
        return workspace_path

    def teardown_method(self, method):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_manage_directory_creates_expected_folder(self):
        """Testet, dass manage_directory den erwarteten Ordner erstellt."""
        workspace_path = self._create_test_workspace()

        self.manage_directory(workspace_path, del_part_log=False)

        expected_directory = os.path.join(workspace_path,
                                          self.EXPECTED_DIRECTORY_NAME)
        assert os.path.isdir(expected_directory)

    def test_manage_directory_existing_directory_logs_warning(self):
        """When del_part_log=False and directory already exists, a WARNING is logged."""
        workspace_path = self._create_test_workspace()
        # First call creates the directory
        self.manage_directory(workspace_path, del_part_log=False)
        DummyLogger.logs.clear()
        # Second call hits the "already exists" branch
        self.manage_directory(workspace_path, del_part_log=False)
        warning_logs = [m for m, level in DummyLogger.logs if level == "WARNING"]
        assert warning_logs, "Expected a WARNING log when directory already exists"

    def test_manage_directory_del_part_log_true_deletes_and_recreates(self):
        """When del_part_log=True, the existing directory is deleted and recreated."""
        workspace_path = self._create_test_workspace()
        # Pre-create the result directory with a marker file
        result_dir = os.path.join(workspace_path, self.EXPECTED_DIRECTORY_NAME)
        os.makedirs(result_dir, exist_ok=True)
        marker = os.path.join(result_dir, "marker.txt")
        open(marker, "w").close()
        # Call with del_part_log=True → directory is deleted and recreated fresh
        self.manage_directory(workspace_path, del_part_log=True)
        assert os.path.isdir(result_dir)
        # The marker file should be gone (directory was recreated)
        assert not os.path.exists(marker)

    def test_manage_directory_exception_is_handled_gracefully(self):
        """An OSError during directory deletion must be caught and logged as CRITICAL."""
        workspace_path = self._create_test_workspace()
        result_dir = os.path.join(workspace_path, self.EXPECTED_DIRECTORY_NAME)
        os.makedirs(result_dir, exist_ok=True)
        DummyLogger.logs.clear()
        with patch("ibtool.helpers.system_utils.shutil.rmtree",
                   side_effect=OSError("Permission denied")):
            self.manage_directory(workspace_path, del_part_log=True)
        critical_logs = [m for m, level in DummyLogger.logs if level == "CRITICAL"]
        assert critical_logs, "Expected a CRITICAL log when shutil.rmtree raises"


# ── save_temp_layer_to_gpkg ───────────────────────────────────────────────────

class TestSaveTempLayerToGpkg:
    """Tests for system_utils.save_temp_layer_to_gpkg."""

    def setup_method(self, method):
        self.tmp = tempfile.TemporaryDirectory()
        from ibtool.helpers.system_utils import save_temp_layer_to_gpkg
        self.save_func = save_temp_layer_to_gpkg
        from ibtool.helpers import system_utils
        self.patcher = patch.object(system_utils, "Logger", DummyLogger)
        self.patcher.start()

    def teardown_method(self, method):
        self.patcher.stop()
        self.tmp.cleanup()

    def _make_valid_layer(self) -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "test", "memory")
        f = QgsFeature()
        f.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0), QgsPointXY(10, 0),
                    QgsPointXY(10, 10), QgsPointXY(0, 10),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_returns_none_for_non_layer_input(self):
        """Passing a non-QgsVectorLayer must return None without crashing."""
        result = self.save_func("not_a_layer", "test", self.tmp.name)
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_invalid_layer(self):
        """An invalid layer (bad path) must return None."""
        invalid = QgsVectorLayer("/nonexistent/path.gpkg", "bad", "ogr")
        result = self.save_func(invalid, "test", self.tmp.name)
        assert result is None

    @pytest.mark.unit
    def test_creates_workspace_directory_if_missing(self):
        new_ws = os.path.join(self.tmp.name, "new_workspace")
        layer = self._make_valid_layer()
        self.save_func(layer, "layer_name", new_ws)
        assert os.path.isdir(new_ws)

    @pytest.mark.integration
    def test_returns_gpkg_path_for_valid_layer(self):
        """A valid layer write must return the expected .gpkg path."""
        layer = self._make_valid_layer()
        result = self.save_func(layer, "my_layer", self.tmp.name)
        expected = os.path.join(self.tmp.name, "my_layer.gpkg")
        assert result == expected

    @pytest.mark.integration
    def test_gpkg_file_is_created_on_disk(self):
        layer = self._make_valid_layer()
        result = self.save_func(layer, "disk_test", self.tmp.name)
        assert result is not None
        assert os.path.isfile(result)


# ── copy_shapefile ────────────────────────────────────────────────────────────

class TestCopyShapefile:
    """Tests for system_utils.copy_shapefile."""

    def setup_method(self, method):
        self.tmp = tempfile.TemporaryDirectory()
        from ibtool.helpers.system_utils import copy_shapefile
        self.copy_func = copy_shapefile

    def teardown_method(self, method):
        self.tmp.cleanup()

    def _create_fake_shapefile(self, folder: str, name: str, extensions=None):
        """Create empty files mimicking shapefile components."""
        if extensions is None:
            extensions = [".shp", ".shx", ".dbf"]
        os.makedirs(folder, exist_ok=True)
        for ext in extensions:
            open(os.path.join(folder, name + ext), "w").close()

    @pytest.mark.unit
    def test_copies_shp_to_target(self):
        src = os.path.join(self.tmp.name, "src")
        dst = os.path.join(self.tmp.name, "dst")
        self._create_fake_shapefile(src, "roads")
        self.copy_func(src, "roads", dst)
        assert os.path.isfile(os.path.join(dst, "roads.shp"))

    @pytest.mark.unit
    def test_returns_path_to_shp_file(self):
        src = os.path.join(self.tmp.name, "src")
        dst = os.path.join(self.tmp.name, "dst")
        self._create_fake_shapefile(src, "roads")
        result = self.copy_func(src, "roads", dst)
        assert result == os.path.join(dst, "roads.shp")

    @pytest.mark.unit
    def test_creates_target_directory_if_missing(self):
        src = os.path.join(self.tmp.name, "src")
        dst = os.path.join(self.tmp.name, "brand_new_dst")
        self._create_fake_shapefile(src, "roads")
        self.copy_func(src, "roads", dst)
        assert os.path.isdir(dst)

    @pytest.mark.unit
    def test_skips_missing_extensions_without_error(self):
        """Extensions that don't exist on disk are skipped silently."""
        src = os.path.join(self.tmp.name, "src")
        dst = os.path.join(self.tmp.name, "dst")
        # Only .shp and .shx — no .dbf, .prj, etc.
        self._create_fake_shapefile(src, "roads", extensions=[".shp", ".shx"])
        self.copy_func(src, "roads", dst)
        assert os.path.isfile(os.path.join(dst, "roads.shp"))
        assert not os.path.isfile(os.path.join(dst, "roads.dbf"))

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_raises_file_not_found_when_shp_missing(self):
        """If the .shp component is absent, FileNotFoundError must be raised."""
        src = os.path.join(self.tmp.name, "src")
        dst = os.path.join(self.tmp.name, "dst")
        os.makedirs(src)
        # Only .dbf — no .shp
        open(os.path.join(src, "roads.dbf"), "w").close()
        with pytest.raises(FileNotFoundError):
            self.copy_func(src, "roads", dst)


# ── get_feature_count ─────────────────────────────────────────────────────────

class TestGetFeatureCount:
    """Tests for system_utils.get_feature_count."""

    def setup_method(self, method):
        from ibtool.helpers.system_utils import get_feature_count
        self.get_count = get_feature_count
        from ibtool.helpers import system_utils
        self.patcher = patch.object(system_utils, "Logger", DummyLogger)
        self.patcher.start()

    def teardown_method(self, method):
        self.patcher.stop()

    def _make_layer_with_n_features(self, n: int) -> QgsVectorLayer:
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "test", "memory")
        feats = []
        for i in range(n):
            f = QgsFeature()
            x = float(i * 20)
            f.setGeometry(
                QgsGeometry.fromPolygonXY(
                    [[
                        QgsPointXY(x, 0), QgsPointXY(x + 10, 0),
                        QgsPointXY(x + 10, 10), QgsPointXY(x, 10),
                        QgsPointXY(x, 0),
                    ]]
                )
            )
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_returns_correct_count(self):
        layer = self._make_layer_with_n_features(3)
        assert self.get_count(layer) == 3

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_zero_for_empty_layer(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "empty", "memory")
        assert self.get_count(layer) == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_raises_runtime_error_for_invalid_layer(self):
        """An invalid layer (isValid() returns False) must raise RuntimeError."""
        mock_layer = Mock()
        mock_layer.isValid.return_value = False
        with pytest.raises(RuntimeError):
            self.get_count(mock_layer)


# ── version_check ─────────────────────────────────────────────────────────────

class TestVersionCheck:
    """Tests for system_utils.version_check."""

    def setup_method(self, method):
        from ibtool.helpers.system_utils import version_check
        self.version_check = version_check

    @pytest.mark.unit
    def test_passes_in_valid_environment(self):
        """In a correctly configured QGIS+Python environment, no exception is raised."""
        self.version_check()  # Must not raise

    @pytest.mark.unit
    def test_raises_for_python_too_old(self):
        import ibtool.helpers.system_utils as su
        with patch.object(su, "sys") as mock_sys:
            mock_sys.version_info = (3, 8, 0, "final", 0)
            with pytest.raises(RuntimeError, match="Python"):
                self.version_check()

    @pytest.mark.unit
    def test_raises_for_python_too_new(self):
        import ibtool.helpers.system_utils as su
        with patch.object(su, "sys") as mock_sys:
            mock_sys.version_info = (3, 13, 0, "final", 0)
            with pytest.raises(RuntimeError, match="Python"):
                self.version_check()

    @pytest.mark.unit
    def test_raises_for_qgis_too_old(self):
        import ibtool.helpers.system_utils as su
        with patch.object(su, "sys") as mock_sys:
            mock_sys.version_info = (3, 11, 0, "final", 0)
            with patch.object(su, "Qgis") as mock_qgis:
                mock_qgis.QGIS_VERSION_INT = 33000
                with pytest.raises(RuntimeError, match="QGIS"):
                    self.version_check()

    @pytest.mark.unit
    def test_raises_for_qgis_too_new(self):
        import ibtool.helpers.system_utils as su
        with patch.object(su, "sys") as mock_sys:
            mock_sys.version_info = (3, 11, 0, "final", 0)
            with patch.object(su, "Qgis") as mock_qgis:
                mock_qgis.QGIS_VERSION_INT = 36000
                with pytest.raises(RuntimeError, match="QGIS"):
                    self.version_check()
