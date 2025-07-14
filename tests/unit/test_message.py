import os
import sys
import types
import unittest

# Dummy QGIS classes
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

class MessageTestCase(unittest.TestCase):
    def setUp(self):
        # Korrekte Pfadberechnung: Von tests/unit/test_message.py zum Projektroot
        # __file__ ist .../tests/unit/test_message.py
        # os.path.dirname(__file__) ist .../tests/unit/
        # os.path.dirname(os.path.dirname(__file__)) ist .../tests/
        # os.path.dirname(os.path.dirname(os.path.dirname(__file__))) ist das Projektroot
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # Prepare minimal helpers package without executing its __init__
        helpers_pkg = types.ModuleType('helpers')
        helpers_pkg.__path__ = [os.path.join(project_root, 'helpers')]
        sys.modules['helpers'] = helpers_pkg

        # Stub qgis modules
        core_mod = types.SimpleNamespace(Qgis=DummyQgis)
        utils_mod = types.SimpleNamespace(QgsMessageLog=DummyQgsMessageLog)
        sys.modules['qgis.core'] = core_mod
        sys.modules['qgis.utils'] = utils_mod
        sys.modules['qgis'] = types.SimpleNamespace(core=core_mod, utils=utils_mod)

        import importlib.util
        message_path = os.path.join(project_root, 'helpers', 'message.py')
        
        # Debug: Pfad überprüfen
        print(f"Debug: Suche message.py unter: {message_path}")
        print(f"Debug: Datei existiert: {os.path.exists(message_path)}")
        
        if not os.path.exists(message_path):
            raise FileNotFoundError(f"message.py nicht gefunden unter: {message_path}")
        
        spec = importlib.util.spec_from_file_location('helpers.message', message_path)
        message_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(message_mod)
        sys.modules['helpers.message'] = message_mod
        self.message_mod = message_mod
        DummyQgsMessageLog.logs.clear()

    def tearDown(self):
        for mod in ['helpers.message', 'helpers', 'qgis.core', 'qgis.utils', 'qgis']:
            sys.modules.pop(mod, None)

    def test_msg_logs_string(self):
        self.message_mod.msg('hello')
        self.assertEqual(DummyQgsMessageLog.logs[-1], ('hello', 'Meldungen', DummyQgis.Info))

    def test_msg_converts_non_string(self):
        self.message_mod.msg(123, level=DummyQgis.Warning)
        self.assertEqual(DummyQgsMessageLog.logs[-1], ('123', 'Meldungen', DummyQgis.Warning))

if __name__ == '__main__':
    unittest.main()