# Plugin Architecture

## Overview

IBTool is a QGIS plugin for settlement delineation based on building footprints. It follows the standard QGIS plugin pattern with a clear separation between UI components and processing logic.

## Entry Point

The plugin is loaded by QGIS via `__init__.py`, which imports the main class:

```python
from .ibtool.ibtool import IBTool
```

QGIS calls `classFactory(iface)` to instantiate the plugin, passing the `QgisInterface` object.

## Main Class: `IBTool` (ibtool/ibtool.py)

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

## UI / Logic Separation

| Layer | Location | Responsibility |
|-------|----------|----------------|
| UI Dialog | `ibtool/ibtool_dialog.py` | Qt widget layout, signal/slot wiring |
| UI Definition | `ibtool/ibtool_dialog_base.ui` | Qt Designer layout file |
| Main Controller | `ibtool/ibtool.py` | Orchestrates UI and tools |
| Processing Tools | `ibtool_tools/*.py` | Stateless geospatial algorithms |
| Helpers | `helpers/*.py` | Shared utilities (logging, geometry, config) |

## Processing Pipeline

The main class reads user inputs from the dialog, resolves layer references, and delegates work to stateless processing tools in `ibtool_tools/`. Each tool receives input layers and parameters, performs geometric operations via QGIS Processing, and returns result layers.

## Package Layout

```
ibtool/                    # Plugin root (QGIS package name)
├── __init__.py           # classFactory() entry point
├── helpers/              # Shared utility modules
├── ibtool_tools/         # Processing tool modules
├── ibtool/               # Nested package for main class + dialog
├── test/                 # Test suite
└── docs/                 # Documentation (this directory)
```

## Import Strategy

- **Root-level modules** (`helpers/`, `ibtool_tools/`): Use relative imports within their package
- **Main class** (`ibtool/ibtool.py`): Uses absolute imports (`from ibtool.helpers...`) because helpers and tools are sibling packages, not parents
- **Tests**: `conftest.py` adds the plugin root to `sys.path`

## Configuration

User-configurable settings (workspace path, log level, layer selections) are managed through the dialog UI and persisted via `helpers/config_manager.py`. Technical QGIS parameters (buffer segments, precision) are centralized in `helpers/qgis_defaults.py`.

## Key Configuration Files

| File | Purpose |
|------|---------|
| `metadata.txt` | Plugin metadata for QGIS plugin repository |
| `pb_tool.cfg` | Plugin Builder tool configuration |
| `Dockerfile` | Containerized test environment setup |
| `Makefile` | Build automation and development tasks |
| `compile.bat` | Windows compilation script |
| `.github/workflows/ci.yml` | Continuous integration pipeline |

## Plugin Installation Paths

- **Windows**: `C:\Users\<User>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
- **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:

1. Builds Docker image with QGIS 3.40 environment
2. Installs all Python dependencies
3. Runs pytest test suite with coverage
4. Uploads coverage reports to Codecov

## Input Data Requirements

The plugin expects specific layer types:

| Layer | Type | Description |
|-------|------|-------------|
| **HU** | Polygon | Building footprint polygons (Hausumringe) |
| **RN** | LineString | Road network linestrings |
| **Part** | Polygon | Partitioning/zoning polygons |
| **Aux** | varies | Auxiliary analysis layers |
| **Filter File** | Text | Positive/negative filtering criteria |

All input layers must use the same coordinate reference system (CRS).
