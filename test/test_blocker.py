import unittest
from unittest.mock import patch, MagicMock

# Dummy classes used for tests
class DummyFeature:
    def __init__(self, fid):
        self._id = fid
        self.attrs = {}

    def id(self):
        return self._id

    def __getitem__(self, key):
        return self.attrs.get(key)

    def __setitem__(self, key, value):
        self.attrs[key] = value


class DummyField:
    def __init__(self, name, *args, **kwargs):
        self._name = name

    def name(self):
        return self._name


class DummyProvider:
    def __init__(self):
        self.fields = {}

    def fieldNameIndex(self, name):
        return 0 if name in self.fields else -1

    def addAttributes(self, attrs):
        for f in attrs:
            self.fields[f.name()] = f


class DummyLayer:
    def __init__(self, features, selected=None):
        self._features = {f.id(): f for f in features}
        self._selected = set(selected or [])
        self._provider = DummyProvider()

    def startEditing(self):
        pass

    def commitChanges(self):
        pass

    def selectedFeatureIds(self):
        return list(self._selected)

    def getFeatures(self):
        return list(self._features.values())

    def deleteFeature(self, fid):
        self._features.pop(fid, None)

    def dataProvider(self):
        return self._provider

    def updateFields(self):
        pass

    def updateFeature(self, feature):
        self._features[feature.id()] = feature

    def featureCount(self):
        return len(self._features)


def get_blocker():
    """Import Blocker module without loading heavy deps."""
    import importlib.util, types, sys
    sys.modules.setdefault('pkg', types.ModuleType('pkg')).__path__ = ['.']
    sys.modules.setdefault('pkg.ibtool_tools', types.ModuleType('pkg.ibtool_tools')).__path__ = ['ibtool_tools']
    sys.modules.setdefault('pkg.helpers', types.ModuleType('pkg.helpers')).__path__ = ['helpers']
    sys.modules.setdefault('ibtool_tools', types.ModuleType('ibtool_tools')).__path__ = ['ibtool_tools']
    sys.modules.setdefault('ibtool_tools.helpers', types.ModuleType('ibtool_tools.helpers')).__path__ = ['helpers']
    helpers_pkg = types.ModuleType('helpers')
    helpers_pkg.__path__ = ['helpers']
    sys.modules['helpers'] = helpers_pkg
    dummy_geom = types.ModuleType('ibtool_tools.helpers.geometry_utils')
    dummy_geom.create_polygons_from_lines = lambda *a, **k: None
    dummy_geom.extract_polygons_from_lines = lambda *a, **k: None
    sys.modules['ibtool_tools.helpers.geometry_utils'] = dummy_geom
    sys.modules['pkg.helpers.geometry_utils'] = dummy_geom
    logger_spec = importlib.util.spec_from_file_location('helpers.logger', 'helpers/logger.py')
    logger_mod = importlib.util.module_from_spec(logger_spec)
    logger_mod.__package__ = 'pkg.helpers'
    logger_spec.loader.exec_module(logger_mod)
    sys.modules['pkg.helpers.logger'] = logger_mod
    sys.modules['helpers.logger'] = logger_mod
    sys.modules['ibtool_tools.helpers.logger'] = logger_mod

    message_spec = importlib.util.spec_from_file_location('helpers.message', 'helpers/message.py')
    message_mod = importlib.util.module_from_spec(message_spec)
    message_mod.__package__ = 'pkg.helpers'
    message_spec.loader.exec_module(message_mod)
    sys.modules['pkg.helpers.message'] = message_mod
    sys.modules['helpers.message'] = message_mod

    # provide a dummy processing module to allow import
    proc_mod = types.ModuleType('processing')
    proc_mod.run = lambda *a, **k: None
    sys.modules['processing'] = proc_mod

    spec = importlib.util.spec_from_file_location('ibtool_tools.Blocker', 'ibtool_tools/Blocker.py')
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = 'pkg.ibtool_tools'
    sys.modules['ibtool_tools.Blocker'] = mod
    spec.loader.exec_module(mod)
    # replace QgsField and QMetaType for simpler dummy versions
    mod.QgsField = DummyField
    class DummyMeta:
        QString = str
    mod.QMetaType = DummyMeta
    return mod


class BlockerUnitTest(unittest.TestCase):
    def setUp(self):
        self.module = get_blocker()

    @patch('ibtool_tools.Blocker.Logger')
    @patch('ibtool_tools.Blocker.processing')
    def test_blocker_basic(self, mock_processing, mock_logger):
        blocks = DummyLayer([DummyFeature(1), DummyFeature(2)], selected=[1])
        mock_processing.run.side_effect = [
            {'OUTPUT': 'outline'},
            {'OUTPUT': 'intersect'},
            {'OUTPUT': 'merge'},
            {'OUTPUT': blocks},
            None
        ]

        result = self.module.blocker('roads', 'buildings', 'partition')
        self.assertIs(result, blocks)
        self.assertEqual(result.featureCount(), 1)
        feature = result.getFeatures()[0]
        self.assertEqual(feature['NAME'], 'Block_1')
        # ensure processing.run called expected algorithms
        algs = [call.args[0] for call in mock_processing.run.call_args_list[:4]]
        self.assertEqual(algs, ['native:polygonstolines', 'native:intersection', 'native:mergevectorlayers', 'native:polygonize'])


class BlockerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.module = get_blocker()

    @patch('ibtool_tools.Blocker.processing')
    def test_integration_flow(self, mock_processing):
        blocks = DummyLayer([DummyFeature(3), DummyFeature(4)], selected=[3])
        mock_processing.run.side_effect = [
            {'OUTPUT': 'outline'},
            {'OUTPUT': 'intersect'},
            {'OUTPUT': 'merge'},
            {'OUTPUT': blocks},
            None
        ]
        result = self.module.blocker('roads', 'buildings', 'partition')
        self.assertEqual(result.featureCount(), 1)
        names = [f['NAME'] for f in result.getFeatures()]
        self.assertEqual(names, ['Block_3'])


if __name__ == '__main__':
    unittest.main()

