import os
import sys
import unittest
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

class LoggerTestCase(unittest.TestCase):
    def setUp(self):
        # Temporary directory for log files
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dummy_msg = DummyMsg()

        # Korrekte Pfadberechnung: Von tests/unit/test_logger.py zum Projektroot
        # __file__ ist .../tests/unit/test_logger.py
        # os.path.dirname(__file__) ist .../tests/unit/
        # os.path.dirname(os.path.dirname(__file__)) ist .../tests/
        # os.path.dirname(os.path.dirname(os.path.dirname(__file__))) ist das Projektroot
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

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
        logger_path = os.path.join(project_root, 'helpers', 'logger.py')
        
        # Debug: Pfad überprüfen
        print(f"Debug: Suche logger.py unter: {logger_path}")
        print(f"Debug: Datei existiert: {os.path.exists(logger_path)}")
        
        if not os.path.exists(logger_path):
            raise FileNotFoundError(f"logger.py nicht gefunden unter: {logger_path}")
        
        spec = importlib.util.spec_from_file_location('helpers.logger', logger_path)
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

    def tearDown(self):
        self.time_patcher.stop()
        
        # Logger-Instanz explizit schließen bevor Module entfernt werden
        if hasattr(self.logger_mod, 'Logger') and self.logger_mod.Logger._instance:
            self.logger_mod.Logger.close_logger()
        
        for mod in ['helpers.logger', 'helpers.message', 'helpers', 'qgis.core', 'qgis']:
            sys.modules.pop(mod, None)
        
        self.tmpdir.cleanup()

    def test_log_file_created(self):
        log_file = os.path.join(self.tmpdir.name, 'logfile_2000-01-01_00-00-00.txt')
        self.assertTrue(os.path.exists(log_file))

    def test_log_writes_and_message_box(self):
        box = DummyMessageBox()
        self.logger_mod.Logger.set_message_box(box)
        start_count = len(self.dummy_msg.messages)
        self.logger.log('hello world', level='INFO')
        self.assertIn('INFO: hello world', box.texts)
        self.assertEqual(DummyQgsMessageLog.logs[-1], ('hello world', 'IBTool', DummyQgis.Info))
        self.assertEqual(len(self.dummy_msg.messages), start_count)  # msg() not used when message_box present

    def test_set_log_level_invalid(self):
        with self.assertRaises(ValueError):
            self.logger_mod.Logger.set_log_level('BAD')

    def test_qgis_level_mapping(self):
        self.assertEqual(self.logger_mod.Logger._qgis_level('INFO'), DummyQgis.Info)
        self.assertEqual(self.logger_mod.Logger._qgis_level('WARNING'), DummyQgis.Warning)
        self.assertEqual(self.logger_mod.Logger._qgis_level('CRITICAL'), DummyQgis.Critical)
        self.assertEqual(self.logger_mod.Logger._qgis_level('SUCCESS'), DummyQgis.Success)

if __name__ == '__main__':
    unittest.main()