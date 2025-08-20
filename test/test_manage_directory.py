import os
import tempfile
from unittest.mock import patch

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

