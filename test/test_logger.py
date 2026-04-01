"""Tests for helpers/logger.py - Logger singleton class.

Coverage:
- Log file creation on initialization
- Log routing to QgsMessageLog (INFO / WARNING / CRITICAL)
- Message box integration and fallback to msg()
- Log level filtering
- close_logger() idempotency
- set_log_dir() switching file handler
- Singleton identity
- Non-string message coercion
"""

import importlib.util
import logging
import os
import sys
import tempfile
import types
from unittest.mock import patch

import pytest

from .config import PROJECT_ROOT

# pylint: disable=attribute-defined-outside-init,consider-using-with,protected-access,too-few-public-methods


class DummyQgis:
    """Minimal QGIS level enum stub for logger tests."""

    Info = 1
    Warning = 2
    Critical = 3
    Success = 4


class DummyQgsMessageLog:
    """Capture QGIS log calls made by the logger."""

    logs = []

    @classmethod
    def logMessage(cls, message, tag, level=None):  # pylint: disable=invalid-name
        """Store a QGIS log entry."""
        cls.logs.append((message, tag, level))


class DummyMsg:
    """Collect fallback messages sent through helpers.message.msg."""

    def __init__(self):
        """Initialize the message sink."""
        self.messages = []

    def __call__(self, message, level=None):
        """Store one fallback message."""
        self.messages.append((message, level))


class DummyMessageBox:
    """In-memory stand-in for a QPlainTextEdit widget."""

    def __init__(self):
        """Initialize the message buffer."""
        self.texts = []

    def appendPlainText(self, text):  # pylint: disable=invalid-name
        """Append one rendered log line."""
        self.texts.append(text)


class TestLogger:
    """Unit tests for the Logger singleton."""

    def setup_method(self, _method):
        """Create isolated module stubs and a fresh Logger singleton."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dummy_msg = DummyMsg()

        project_root = str(PROJECT_ROOT)

        helpers_pkg = types.ModuleType('helpers')
        helpers_pkg.__path__ = [os.path.join(project_root, 'helpers')]
        sys.modules['helpers'] = helpers_pkg

        message_mod = types.ModuleType('helpers.message')
        message_mod.msg = self.dummy_msg
        sys.modules['helpers.message'] = message_mod

        core = types.SimpleNamespace(Qgis=DummyQgis, QgsMessageLog=DummyQgsMessageLog)
        sys.modules['qgis.core'] = core
        sys.modules['qgis'] = types.SimpleNamespace(core=core)

        spec = importlib.util.spec_from_file_location(
            'helpers.logger',
            os.path.join(project_root, 'helpers', 'logger.py'),
        )
        logger_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger_mod)
        sys.modules['helpers.logger'] = logger_mod
        self.logger_mod = logger_mod

        self.time_patcher = patch(
            'helpers.logger.time.strftime',
            return_value='2000-01-01_00-00-00',
        )
        self.time_patcher.start()

        self.logger_mod.Logger._instance = None
        self.logger_mod.Logger.log_dir = None
        self.logger_mod.Logger.file_handler = None
        self.logger = self.logger_mod.Logger()
        DummyQgsMessageLog.logs.clear()

    def teardown_method(self, _method):
        """Tear down module stubs and temporary files."""
        self.time_patcher.stop()

        if hasattr(self.logger_mod, 'Logger') and self.logger_mod.Logger._instance:
            self.logger_mod.Logger.close_logger()

        for mod in ['helpers.logger', 'helpers.message', 'helpers', 'qgis.core', 'qgis']:
            sys.modules.pop(mod, None)

        self.tmpdir.cleanup()

    @pytest.mark.unit
    def test_log_file_created_after_set_log_dir(self):
        """Creates a log file only after set_log_dir() is called."""
        self.logger_mod.Logger.set_log_dir(self.tmpdir.name)
        log_file = os.path.join(self.tmpdir.name, 'logfile_2000-01-01_00-00-00.txt')
        assert os.path.exists(log_file)

    @pytest.mark.unit
    def test_no_log_file_created_on_plain_initialization(self):
        """Logger() alone must not create a file before a log directory is selected."""
        log_file = os.path.join(self.tmpdir.name, 'logfile_2000-01-01_00-00-00.txt')
        assert not os.path.exists(log_file)

    @pytest.mark.unit
    def test_log_writes_and_message_box(self):
        """Writes a level-prefixed message to the message box and to QgsMessageLog."""
        box = DummyMessageBox()
        self.logger_mod.Logger.set_message_box(box)
        start_count = len(self.dummy_msg.messages)

        self.logger.log('hello world', level='INFO')

        assert 'INFO: hello world' in box.texts
        assert DummyQgsMessageLog.logs[-1] == ('hello world', 'IBTool', DummyQgis.Info)
        assert len(self.dummy_msg.messages) == start_count

    @pytest.mark.unit
    def test_set_log_level_invalid(self):
        """Raises ValueError when set_log_level receives an unknown level string."""
        with pytest.raises(ValueError):
            self.logger_mod.Logger.set_log_level('BAD')

    @pytest.mark.unit
    def test_qgis_level_mapping(self):
        """Maps INFO/WARNING/CRITICAL/SUCCESS strings to the correct Qgis constants."""
        assert self.logger_mod.Logger._qgis_level('INFO') == DummyQgis.Info
        assert self.logger_mod.Logger._qgis_level('WARNING') == DummyQgis.Warning
        assert self.logger_mod.Logger._qgis_level('CRITICAL') == DummyQgis.Critical
        assert self.logger_mod.Logger._qgis_level('SUCCESS') == DummyQgis.Success

    @pytest.mark.unit
    def test_warning_routed_to_qgis_warning_level(self):
        """log(..., level='WARNING') routes to QgsMessageLog with Qgis.Warning."""
        DummyQgsMessageLog.logs.clear()

        self.logger.log('test warning', level='WARNING')

        assert DummyQgsMessageLog.logs[-1] == (
            'test warning',
            'IBTool',
            DummyQgis.Warning,
        )

    @pytest.mark.unit
    def test_critical_routed_to_qgis_critical_level(self):
        """log(..., level='CRITICAL') routes to QgsMessageLog with Qgis.Critical."""
        DummyQgsMessageLog.logs.clear()

        self.logger.log('test critical', level='CRITICAL')

        assert DummyQgsMessageLog.logs[-1] == (
            'test critical',
            'IBTool',
            DummyQgis.Critical,
        )

    @pytest.mark.unit
    def test_log_file_formatter_produces_expected_format(self):
        """File handler formatter produces 'LEVELNAME HH:MM:SS - message' lines."""
        self.logger_mod.Logger.set_log_dir(self.tmpdir.name)
        handler = self.logger_mod.Logger.file_handler
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='format check',
            args=(),
            exc_info=None,
        )

        line = handler.formatter.format(record)

        assert line.startswith('INFO '), (
            f"Expected line to start with 'INFO ', got: {line!r}"
        )
        assert ' - format check' in line, (
            f"Expected ' - format check' in line, got: {line!r}"
        )

    @pytest.mark.unit
    def test_close_logger_called_twice_does_not_raise(self):
        """close_logger() is idempotent - calling it twice must not raise."""
        self.logger_mod.Logger.close_logger()
        self.logger_mod.Logger.close_logger()

    @pytest.mark.unit
    def test_log_without_message_box_calls_msg(self):
        """When no message box is set, log() calls msg() with a level-prefixed message."""
        self.logger_mod.Logger.message_box = None
        before = len(self.dummy_msg.messages)

        self.logger.log('no box message', level='INFO')

        assert len(self.dummy_msg.messages) > before
        assert self.dummy_msg.messages[-1][0] == 'INFO: no box message'

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        """Calling Logger() twice must return the exact same object."""
        instance1 = self.logger_mod.Logger()
        instance2 = self.logger_mod.Logger()
        assert instance1 is instance2

    @pytest.mark.unit
    def test_set_log_dir_switches_to_new_directory(self):
        """set_log_dir must close the old handler and open a new file in the new directory."""
        new_dir = os.path.join(self.tmpdir.name, 'new_logs')
        os.makedirs(new_dir, exist_ok=True)

        self.logger_mod.Logger.set_log_dir(new_dir)

        assert self.logger_mod.Logger.log_dir == new_dir
        handler = self.logger_mod.Logger.file_handler
        assert handler is not None
        assert new_dir in handler.baseFilename

    @pytest.mark.unit
    def test_message_box_runtime_error_clears_box_and_falls_back_to_msg(self):
        """When appendPlainText raises RuntimeError, message_box is cleared and msg() is used."""

        class BrokenBox:
            """Message box stub that simulates a deleted Qt widget."""

            def appendPlainText(self, _text):  # pylint: disable=invalid-name
                """Raise the same error Qt emits for deleted widgets."""
                raise RuntimeError('Widget deleted')

        self.logger_mod.Logger.set_message_box(BrokenBox())
        before = len(self.dummy_msg.messages)

        self.logger.log('runtime error test', level='INFO')

        assert self.logger_mod.Logger.message_box is None
        assert len(self.dummy_msg.messages) > before

    @pytest.mark.unit
    def test_message_below_configured_threshold_is_suppressed(self):
        """INFO messages must not be emitted when log_level is set to WARNING."""
        self.logger_mod.Logger.log_level = logging.WARNING
        DummyQgsMessageLog.logs.clear()
        before_msg_count = len(self.dummy_msg.messages)

        self.logger.log('suppressed info', level='INFO')

        assert len(DummyQgsMessageLog.logs) == 0
        assert len(self.dummy_msg.messages) == before_msg_count
        self.logger_mod.Logger.log_level = 0

    @pytest.mark.unit
    def test_non_string_message_is_converted_to_string(self):
        """Passing a non-string value must be converted via str() without crashing."""
        box = DummyMessageBox()
        self.logger_mod.Logger.set_message_box(box)

        self.logger.log(12345, level='INFO')

        assert any('12345' in text for text in box.texts)
