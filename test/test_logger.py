import os
import sys
import pytest
import tempfile
import types
from unittest.mock import patch

# Prepare dummy qgis modules
class DummyQgis:
    Info = 1
    Warning = 2
    Critical = 3
    Success = 4

class DummyQgsMessageLog:
    logs = []

    @classmethod
    def logMessage(cls, message, tag, level=None):
        cls.logs.append((message, tag, level))

class DummyMsg:
    def __init__(self):
        self.messages = []

    def __call__(self, message, level=None):
        self.messages.append((message, level))

class DummyMessageBox:
    def __init__(self):
        self.texts = []

    def appendPlainText(self, text):
        self.texts.append(text)

class TestLogger:
    def setup_method(self, method):
        # Temporary directory for log files
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dummy_msg = DummyMsg()

        from .config import PROJECT_ROOT
        project_root = str(PROJECT_ROOT)

        # Create minimal helpers package without running its __init__
        helpers_pkg = types.ModuleType('helpers')
        helpers_pkg.__path__ = [os.path.join(project_root, 'helpers')]
        sys.modules['helpers'] = helpers_pkg

        message_mod = types.ModuleType('helpers.message')
        message_mod.msg = self.dummy_msg
        sys.modules['helpers.message'] = message_mod

        # Stub qgis modules
        core = types.SimpleNamespace(Qgis=DummyQgis, QgsMessageLog=DummyQgsMessageLog)
        sys.modules['qgis.core'] = core
        sys.modules['qgis'] = types.SimpleNamespace(core=core)

        # Load logger module manually
        import importlib.util
        spec = importlib.util.spec_from_file_location('helpers.logger', os.path.join(project_root, 'helpers', 'logger.py'))
        logger_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger_mod)
        sys.modules['helpers.logger'] = logger_mod
        self.logger_mod = logger_mod

        # Deterministic timestamp
        self.time_patcher = patch('helpers.logger.time.strftime', return_value='2000-01-01_00-00-00')
        self.time_patcher.start()

        self.logger_mod.Logger._instance = None
        self.logger_mod.Logger.log_dir = self.tmpdir.name
        self.logger = self.logger_mod.Logger()
        DummyQgsMessageLog.logs.clear()

    def teardown_method(self, method):
        self.time_patcher.stop()
        
        # Logger-Instanz explizit schließen bevor Module entfernt werden
        if hasattr(self.logger_mod, 'Logger') and self.logger_mod.Logger._instance:
            self.logger_mod.Logger.close_logger()
        
        for mod in ['helpers.logger', 'helpers.message', 'helpers', 'qgis.core', 'qgis']:
            sys.modules.pop(mod, None)
        
        self.tmpdir.cleanup()

    def test_log_file_created(self):
        log_file = os.path.join(self.tmpdir.name, 'logfile_2000-01-01_00-00-00.txt')
        assert os.path.exists(log_file)

    def test_log_writes_and_message_box(self):
        box = DummyMessageBox()
        self.logger_mod.Logger.set_message_box(box)
        start_count = len(self.dummy_msg.messages)
        self.logger.log('hello world', level='INFO')
        assert 'INFO: hello world' in box.texts
        assert DummyQgsMessageLog.logs[-1] == ('hello world', 'IBTool', DummyQgis.Info)
        assert len(self.dummy_msg.messages) == start_count  # msg() not used when message_box present

    def test_set_log_level_invalid(self):
        with pytest.raises(ValueError):
            self.logger_mod.Logger.set_log_level('BAD')

    def test_qgis_level_mapping(self):
        assert self.logger_mod.Logger._qgis_level('INFO') == DummyQgis.Info
        assert self.logger_mod.Logger._qgis_level('WARNING') == DummyQgis.Warning
        assert self.logger_mod.Logger._qgis_level('CRITICAL') == DummyQgis.Critical
        assert self.logger_mod.Logger._qgis_level('SUCCESS') == DummyQgis.Success

    def test_warning_routed_to_qgis_warning_level(self):
        """log(..., level='WARNING') routes to QgsMessageLog with Qgis.Warning."""
        DummyQgsMessageLog.logs.clear()
        self.logger.log('test warning', level='WARNING')
        assert DummyQgsMessageLog.logs[-1] == ('test warning', 'IBTool', DummyQgis.Warning)

    def test_critical_routed_to_qgis_critical_level(self):
        """log(..., level='CRITICAL') routes to QgsMessageLog with Qgis.Critical."""
        DummyQgsMessageLog.logs.clear()
        self.logger.log('test critical', level='CRITICAL')
        assert DummyQgsMessageLog.logs[-1] == ('test critical', 'IBTool', DummyQgis.Critical)

    def test_log_file_formatter_produces_expected_format(self):
        """File handler formatter produces 'LEVELNAME HH:MM:SS - message' lines."""
        import logging as _logging
        handler = self.logger_mod.Logger.file_handler
        record = _logging.LogRecord(
            name='test', level=_logging.INFO,
            pathname='', lineno=0,
            msg='format check', args=(), exc_info=None,
        )
        line = handler.formatter.format(record)
        assert line.startswith('INFO '), f"Expected line to start with 'INFO ', got: {line!r}"
        assert ' - format check' in line, f"Expected ' - format check' in line, got: {line!r}"

    def test_close_logger_called_twice_does_not_raise(self):
        """close_logger() is idempotent — calling it twice must not raise."""
        self.logger_mod.Logger.close_logger()
        self.logger_mod.Logger.close_logger()

    def test_log_without_message_box_calls_msg(self):
        """When no message box is set, log() calls msg() with a level-prefixed message."""
        self.logger_mod.Logger.message_box = None
        before = len(self.dummy_msg.messages)
        self.logger.log('no box message', level='INFO')
        assert len(self.dummy_msg.messages) > before
        last_text = self.dummy_msg.messages[-1][0]
        assert last_text == 'INFO: no box message'
