"""
Pytest configuration file for IBTool tests.

This file sets up the Python path BEFORE any test modules are imported.
CRITICAL: Must be executed before test collection!
"""

import sys
import types
from pathlib import Path

# CRITICAL: Add plugin root to sys.path IMMEDIATELY
# This MUST happen before pytest tries to import test modules
plugin_root = Path(__file__).resolve().parent.parent

# Register the plugin root as the 'ibtool' package in sys.modules.
#
# Why: locally the plugin folder is named 'IB-Tool-3', so Python would resolve
# 'ibtool' to the nested ibtool/ subfolder (which has no helpers/ or
# ibtool_tools/).  This stub makes 'ibtool' behave exactly like the Docker /
# QGIS environment where the plugin folder IS named 'ibtool' and its parent
# directory is in PYTHONPATH.  Absolute imports like
# 'from ibtool.helpers.X import Y' and 'from ibtool.ibtool_tools.X import Y'
# then resolve to the correct paths.
if 'ibtool' not in sys.modules:
    _ibtool_pkg = types.ModuleType('ibtool')
    _ibtool_pkg.__path__ = [str(plugin_root)]
    _ibtool_pkg.__package__ = 'ibtool'
    _ibtool_pkg.__file__ = str(plugin_root / '__init__.py')
    sys.modules['ibtool'] = _ibtool_pkg

# Insert at position 0 to ensure it's found first
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
    print(f"✅ conftest.py: Added {plugin_root} to sys.path")
else:
    print(f"ℹ️ conftest.py: {plugin_root} already in sys.path")

# Verify critical directories exist
assert (plugin_root / 'helpers').exists(), f"helpers/ not found in {plugin_root}"
assert (plugin_root / 'ibtool_tools').exists(), f"ibtool_tools/ not found in {plugin_root}"
assert (plugin_root / 'ibtool').exists(), f"ibtool/ not found in {plugin_root}"

print(f"✅ conftest.py: All required directories found")
print(f"   - helpers/: {(plugin_root / 'helpers').exists()}")
print(f"   - ibtool_tools/: {(plugin_root / 'ibtool_tools').exists()}")
print(f"   - ibtool/: {(plugin_root / 'ibtool').exists()}")


# ---------------------------------------------------------------------------
# Shared layer / geometry factory helpers
#
# These live in test/layer_factories.py (a regular Python module, not a
# pytest plugin).  Import them in test files AFTER calling get_qgis_app():
#
#   QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
#   from .layer_factories import (
#       make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer
#   )
#
# Factories must NOT be imported from conftest.py because conftest runs as a
# pytest plugin before QGIS is initialised, and its module context causes
# QGIS' import hook (qgis.utils._import) to trigger a circular-import error.
# ---------------------------------------------------------------------------
