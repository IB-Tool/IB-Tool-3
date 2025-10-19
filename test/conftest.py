"""
Pytest configuration file for IBTool tests.

This file sets up the Python path to allow tests to import from the ibtool package
using absolute imports (e.g., from ibtool.helpers.logger import Logger).
"""

import sys
from pathlib import Path

# Add the plugin root directory to sys.path
# This allows imports like: from ibtool.helpers.logger import Logger
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

# Verify the path was added correctly
print(f"Added to sys.path: {plugin_root}")
print(f"Plugin root exists: {plugin_root.exists()}")
print(f"helpers/ exists: {(plugin_root / 'helpers').exists()}")
print(f"ibtool_tools/ exists: {(plugin_root / 'ibtool_tools').exists()}")
