import os
import sys
import types

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

class TestMessage:
    def setup_method(self, method):
        from .config import PROJECT_ROOT
        project_root = str(PROJECT_ROOT)

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
        spec = importlib.util.spec_from_file_location('helpers.message', os.path.join(project_root, 'helpers', 'message.py'))
        message_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(message_mod)
        sys.modules['helpers.message'] = message_mod
        self.message_mod = message_mod
        DummyQgsMessageLog.logs.clear()

    def teardown_method(self, method):
        for mod in ['helpers.message', 'helpers', 'qgis.core', 'qgis.utils', 'qgis']:
            sys.modules.pop(mod, None)

    def test_msg_logs_string(self):
        self.message_mod.msg('hello')
        assert DummyQgsMessageLog.logs[-1] == ('hello', 'Meldungen', DummyQgis.Info)

    def test_msg_converts_non_string(self):
        self.message_mod.msg(123, level=DummyQgis.Warning)
        assert DummyQgsMessageLog.logs[-1] == ('123', 'Meldungen', DummyQgis.Warning)

    def test_msg_without_message_box_does_not_raise(self):
        """msg() works standalone — it requires no Logger message box to function."""
        # msg() delegates directly to QgsMessageLog; no additional setup must be needed
        try:
            self.message_mod.msg('standalone call')
        except Exception as exc:
            raise AssertionError(f"msg() raised unexpectedly: {exc}")
        assert DummyQgsMessageLog.logs[-1][0] == 'standalone call'

    def test_msg_empty_string(self):
        """msg('') does not raise and logs an empty string."""
        DummyQgsMessageLog.logs.clear()
        self.message_mod.msg('')
        assert len(DummyQgsMessageLog.logs) == 1
        assert DummyQgsMessageLog.logs[-1][0] == ''

    def test_msg_none_coerced_to_string(self):
        """msg(None) coerces the value to the string 'None' before logging."""
        DummyQgsMessageLog.logs.clear()
        self.message_mod.msg(None)
        assert DummyQgsMessageLog.logs[-1][0] == 'None'

