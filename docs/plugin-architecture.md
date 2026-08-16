# Plugin Architecture

IB-Tool 3 follows the standard QGIS plugin pattern with a clear separation between UI components and processing logic. This document covers the code structure, entry points, package layout, and import strategy. For CI/CD and development setup, see [docs/contributing.md](contributing.md). For input layer specifications, see [docs/input-data.md](input-data.md).

---

## Entry Point

The plugin is loaded by QGIS via `__init__.py`, which imports the main class:

```python
from .ibtool.ibtool import IBTool
```

QGIS calls `classFactory(iface)` to instantiate the plugin, passing the `QgisInterface` object.

---

## Main Class: `IBTool` (`ibtool/ibtool.py`)

### `initGui()`

Called by QGIS when the plugin is activated. Responsibilities:

- Creates the plugin toolbar and menu entries
- Initializes the dialog UI (`IBToolDialog`)
- Connects UI signals to processing slots
- Sets up the logging system

### `add_action()`

Registers a single toolbar/menu action:

- Creates a `QAction` with icon, text, and callback
- Adds the action to the plugin toolbar
- Adds the action to the plugin menu under "Plugins"
- Returns the action for further configuration

### `unload()`

Called when the plugin is deactivated:

- Removes all registered menu entries
- Removes the toolbar
- Cleans up resources

---

## UI / Logic Separation

| Layer | Location | Responsibility |
|-------|----------|----------------|
| UI Dialog | `ibtool/ibtool_dialog.py` | Qt widget layout, signal/slot wiring |
| UI Definition | `ibtool/ibtool_dialog_base.ui` | Qt Designer layout file |
| Main Controller | `ibtool/ibtool.py` | Orchestrates UI and tools |
| Processing Tools | `ibtool_tools/*.py` | Stateless geospatial algorithms |
| Helpers | `helpers/*.py` | Shared utilities (logging, geometry, config) |

---

## Processing Pipeline

The main class reads user inputs from the dialog, resolves layer references, and delegates work to stateless processing tools in `ibtool_tools/`. Each tool receives input layers and parameters, performs geometric operations via QGIS Processing, and returns result layers.

For the full step-by-step algorithmic description, see [docs/how-it-works.md](how-it-works.md).

---

## Package Layout

```text
ibtool/                    # Plugin root (QGIS package name)
├── __init__.py           # classFactory() entry point
├── helpers/              # Shared utility modules
├── ibtool_tools/         # Processing tool modules
├── ibtool/               # Nested package for main class + dialog
├── test/                 # Test suite
└── docs/                 # Documentation (this directory)
```

---

## Import Strategy

- **Root-level modules** (`helpers/`, `ibtool_tools/`): Use relative imports within their package
- **Main class** (`ibtool/ibtool.py`): Uses absolute imports (`from ibtool.helpers…`) because helpers and tools are sibling packages, not parents
- **Tests**: `conftest.py` adds the plugin root to `sys.path`

---

## Configuration

User-configurable settings (workspace path, log level, layer selections) are managed through the dialog UI and persisted via `helpers/config_manager.py`. Technical QGIS parameters (buffer segments, precision) are centralized in `helpers/qgis_defaults.py`.

For the full `CONFIG.ini` reference including all sections and keys, see [docs/CONFIG_README.md](CONFIG_README.md).

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `metadata.txt` | Plugin metadata for QGIS plugin repository |
| `pb_tool.cfg` | Plugin Builder tool configuration |
| `Dockerfile` | Containerized test environment setup |
| `Makefile` | Build automation and development tasks |
| `compile.bat` | Windows compilation script |
| `.github/workflows/ci.yml` | Continuous integration pipeline |

---

## Plugin Installation Paths

- **Windows**: `C:\Users\<User>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
- **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`

### Plugin Folder Naming

QGIS loads plugins by importing the folder name as a Python module. This means the plugin folder **must be a valid Python identifier** — only lowercase letters, digits, and underscores are allowed; the name must not start with a digit and must not contain hyphens or dots.

The GitHub repository is named `IB-Tool-3` and the release ZIP packages the plugin under the same folder name. After extracting or cloning, the folder must be **renamed** to `ibtool` for QGIS to recognise it:

```
IB-Tool-3  →  ibtool
```

The plugin's `__init__.py` registers a virtual `ibtool` package at runtime so that absolute imports (`from ibtool.helpers…`) work regardless of the actual folder name on disk. However, QGIS itself must first be able to import the folder — and that import fails if the folder name contains hyphens or dots.

---

## Related Files

| File | Content |
|------|---------|
| [`docs/how-it-works.md`](how-it-works.md) | Full algorithmic pipeline, step-by-step explanation |
| [`docs/input-data.md`](input-data.md) | Input layer specs, field requirements, validation checks |
| [`docs/CONFIG_README.md`](CONFIG_README.md) | `CONFIG.ini` reference — all keys, sections, defaults |
| [`docs/contributing.md`](contributing.md) | CI/CD pipeline, Docker environment, test structure |
| [`docs/error-handling.md`](error-handling.md) | Logging system, error categories, debug mode |
