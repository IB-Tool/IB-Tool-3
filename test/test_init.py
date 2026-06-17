# coding=utf-8
"""Tests QGIS plugin init."""

__author__ = 'Tim Sutton <tim@linfiniti.com>'
__revision__ = '$Format:%H$'
__date__ = '17/10/2010'
__license__ = "GPL"
__copyright__ = 'Copyright 2012, Australia Indonesia Facility for '
__copyright__ += 'Disaster Reduction'

import os
import logging
import configparser
import importlib.util
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

LOGGER = logging.getLogger('QGIS')


class TestInit:
    """Test that the plugin init is usable for QGIS.

    Based heavily on the validator class by Alessandro
    Passoti available here:

    http://github.com/qgis/qgis-django/blob/master/qgis-app/
             plugins/validator.py

    """

    def test_read_init(self):
        """Test that the plugin __init__ will validate on plugins.qgis.org."""

        # You should update this list according to the latest in
        # https://github.com/qgis/qgis-django/blob/master/qgis-app/
        #        plugins/validator.py

        required_metadata = [
            'name',
            'description',
            'version',
            'qgisMinimumVersion',
            'email',
            'author']

        file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), os.pardir,
            'metadata.txt'))
        LOGGER.info(file_path)
        metadata = []
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(file_path)
        message = 'Cannot find a section named "general" in %s' % file_path
        assert parser.has_section('general'), message
        metadata.extend(parser.items('general'))

        for expectation in required_metadata:
            message = (
                'Cannot find metadata "%s" in metadata source (%s).' % (
                    expectation, file_path))

            assert expectation in dict(metadata), message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_root_init():
    """Load IB-Tool-3/__init__.py directly, bypassing the conftest virtual package.

    Returns the module object with _MISSING_PACKAGES, _MissingDepsPlugin,
    and classFactory defined as module-level names.
    """
    init_path = Path(__file__).resolve().parent.parent / "__init__.py"
    spec = importlib.util.spec_from_file_location("_plugin_root_init", init_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# TestMissingDepsPlugin
# ---------------------------------------------------------------------------

class TestMissingDepsPlugin:
    """Tests for the _MissingDepsPlugin stub class in the root __init__.py."""

    @pytest.mark.unit
    def test_missing_packages_is_empty_when_scipy_and_networkx_present(self):
        """In the Docker test env, scipy and networkx are available — list must be empty."""
        mod = _load_root_init()

        assert mod._MISSING_PACKAGES == [], (
            f"Expected no missing packages in test env, got: {mod._MISSING_PACKAGES}"
        )

    @pytest.mark.unit
    def test_initGui_pushes_critical_message(self):
        """_MissingDepsPlugin.initGui must push a Critical message bar entry."""
        mod = _load_root_init()
        mock_iface = MagicMock()

        with patch("qgis.core.Qgis") as mock_qgis:
            mock_qgis.Critical = 2
            plugin = mod._MissingDepsPlugin(mock_iface, ["scipy"])
            plugin.initGui()

        mock_iface.messageBar.return_value.pushMessage.assert_called_once()

    @pytest.mark.unit
    def test_initGui_message_names_all_missing_packages(self):
        """The message bar text must name every package in the missing list."""
        mod = _load_root_init()
        mock_iface = MagicMock()

        with patch("qgis.core.Qgis"):
            plugin = mod._MissingDepsPlugin(mock_iface, ["scipy", "networkx"])
            plugin.initGui()

        call_text = str(mock_iface.messageBar.return_value.pushMessage.call_args)
        assert "scipy" in call_text
        assert "networkx" in call_text

    @pytest.mark.unit
    def test_initGui_message_includes_pip_install_command(self):
        """The message bar text must contain a pip install command."""
        mod = _load_root_init()
        mock_iface = MagicMock()

        with patch("qgis.core.Qgis"):
            plugin = mod._MissingDepsPlugin(mock_iface, ["scipy"])
            plugin.initGui()

        call_text = str(mock_iface.messageBar.return_value.pushMessage.call_args)
        assert "pip install" in call_text

    @pytest.mark.unit
    def test_unload_does_not_raise(self):
        """_MissingDepsPlugin.unload must be a safe no-op."""
        mod = _load_root_init()
        plugin = mod._MissingDepsPlugin(MagicMock(), ["scipy"])

        plugin.unload()  # Must not raise

    @pytest.mark.unit
    def test_classFactory_returns_missing_deps_plugin_when_packages_absent(self):
        """classFactory must return _MissingDepsPlugin when _MISSING_PACKAGES is non-empty."""
        mod = _load_root_init()
        mod._MISSING_PACKAGES = ["scipy"]

        result = mod.classFactory(MagicMock())

        assert isinstance(result, mod._MissingDepsPlugin)

