# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. For detailed rules and domain knowledge, consult the referenced files in `ai/` and `docs/`.

## Project Overview

**IBTool** is a QGIS plugin for settlement delineation based on building footprints. It provides automated geospatial processing tools for urban planning and settlement analysis (clustering, density calculations, MST analysis). The plugin is prepared for publication on plugins.qgis.org.

## Package Structure

```
ibtool/                    # Plugin root (QGIS package)
├── __init__.py           # QGIS entry point (from .ibtool.ibtool import IBTool)
├── helpers/              # Shared utility modules
│   ├── logger.py        # Logging system
│   ├── data_loader.py   # Geodata loading and validation
│   ├── geometry_utils.py # Spatial geometry operations
│   ├── system_utils.py  # System path and environment utilities
│   ├── message.py       # User messaging system
│   ├── config_manager.py # Configuration management
│   ├── qgis_defaults.py # QGIS technical parameters
│   ├── mst_utils.py     # MST utility functions
│   └── edge_catch_utils.py # Edge detection utilities
├── ibtool_tools/        # Processing tools
│   ├── Blocker.py       # Settlement blocking and partitioning
│   ├── CreateMST.py     # Minimum spanning tree creation
│   ├── MST_Clustering.py # MST-based clustering
│   ├── FootprintDensity.py # Building density calculations
│   ├── ImportFilter.py  # Data filtering and preprocessing
│   ├── GapClose.py      # Gap closing
│   ├── HoleClose.py     # Hole closing
│   ├── EdgeCatch.py     # Edge detection
│   ├── AddSingleBuilding.py # Single building processing
│   ├── ErodeEmptyAreas.py # Building-free void removal
│   └── PatchRemove.py   # Patch removal
├── ibtool/              # Nested package for main plugin class
│   ├── ibtool.py        # Main plugin class
│   └── ibtool_dialog.py # UI dialog
├── docs/                # Project documentation
├── ai/                  # AI rules, domain knowledge, task templates
└── test/                # Test suite
```

## Import System

```python
# In ROOT-level modules (helpers/, ibtool_tools/) — RELATIVE imports
from .logger import Logger
from .message import msg

# In ibtool/ibtool.py — ABSOLUTE imports (siblings, not parents!)
from ibtool.helpers.logger import Logger
from ibtool.ibtool_tools.Blocker import blocker
from ibtool.ibtool.ibtool_dialog import IBToolDialog

# For tests: test/conftest.py adds plugin root to sys.path
```

**Docker**: Plugin must be at `/plugins/ibtool/` with `PYTHONPATH=/plugins` to mirror QGIS package resolution.

## Common Development Commands

```bash
# Tests (Docker — recommended)
docker build -t qgis-plugin-test .
docker run --rm qgis-plugin-test

# Tests (local)
pytest test/ -v
pytest test/test_blocker.py -v
pytest test/ --cov=. --cov-report=html

# Build
compile.bat                # Windows
pb_tool compile && pb_tool deploy  # Cross-platform
make compile && make deploy        # Linux/Mac

# Code quality
make pep8
make pylint
```

## Prerequisites

- QGIS 3.40–3.50, Python 3.11+
- Runtime dependencies: numpy, scipy, networkx, PyQt5
  - numpy and PyQt5 are bundled with QGIS 3.40+
  - scipy and networkx may not be present depending on the QGIS installation and platform — install manually if needed (`pip install scipy networkx`)
- Dev/test dependencies (not bundled): pytest, pytest-cov (see requirements-dev.txt)

## Important Notes

- Never add dependencies without prior consultation
- Keep processing algorithms stateless and testable
- Use the centralized logging system for all output (not print)
- All changes should include appropriate tests
- Update `docs/CHANGELOG.md` for significant changes
- verifiy your changes. If verification is not possible, give tipps to verify it

## Detailed Documentation

For task-specific rules and deeper context, consult these files:

### `docs/` — Project Documentation
| File | Content |
|------|---------|
| [plugin-architecture.md](docs/plugin-architecture.md) | Plugin structure, entry points, UI/logic separation, package layout, import strategy |
| [how-it-works.md](docs/how-it-works.md) | Full processing pipeline, step-by-step explanation with pseudocode, output |
| [error-handling.md](docs/error-handling.md) | Logging system, error categories, safe_processing_run, debug mode |
| [test-strategy.md](docs/test-strategy.md) | Test taxonomy, coverage targets, module-to-test mapping, gap backlog |
| [contributing.md](docs/contributing.md) | CI/CD setup, Docker environment, test structure, code linting |
| [parameterization.md](docs/parameterization.md) | Full parameter reference: defaults, sensitivity, academic background |
| [input-data.md](docs/input-data.md) | Input layer specs, field requirements, filter file format, validation checks |
| [CONFIG_README.md](docs/CONFIG_README.md) | CONFIG.ini reference — all sections, keys, and defaults |
| [CHANGELOG.md](docs/CHANGELOG.md) | Full version history of all notable changes |

### `ai/core/` — Binding Rules for All Code Changes
| File | Content |
|------|---------|
| [constraints.md](ai/core/constraints.md) | Interface access, statefulness, documentation, paths, dependencies, error handling |
| [naming-conventions.md](ai/core/naming-conventions.md) | snake_case/PascalCase rules, abbreviations, layer names, file names |
| [testing-rules.md](ai/core/testing-rules.md) | Pre-change checks, geometry test patterns, coverage, test structure |
| [qgis-api-rules.md](ai/core/qgis-api-rules.md) | QgsVectorLayer, QgsFeature, QgsGeometry, Processing algorithms, API compatibility |
| [architecture-guidelines.md](ai/core/architecture-guidelines.md) | Parameter management, class design, code organization, usage patterns |
| [debug-mode.md](ai/core/debug-mode.md) | Debug-Modus integration, _dbg dict pattern, save_debug_layer conventions |
| [release-conventions.md](ai/core/release-conventions.md) | metadata.txt invariants, LICENSE file, release ZIP, CI requirements |

### `ai/domain/` — Domain-Specific Knowledge
| File | Content |
|------|---------|
| [geometry-validation.md](ai/domain/geometry-validation.md) | Null/empty/validity checks, multipart handling, self-intersection, topology |
| [feature-processing.md](ai/domain/feature-processing.md) | Feature iteration, attribute joins, field calculator, ID handling, layer creation |
| [mst-architecture.md](ai/domain/mst-architecture.md) | Current MST module state, target architecture, refactoring plan |
| [mst-testing.md](ai/domain/mst-testing.md) | MST test files, fixtures, markers, performance benchmarks, known issues |
| [gap-close.md](ai/domain/gap-close.md) | GapClose design decisions, dissolve/dissolve-in-large-layer workarounds, constants |

### `ai/tasks/` — Task Templates
| File | When to use |
|------|-------------|
| [bugfix-task.md](ai/tasks/bugfix-task.md) | Fixing a bug — minimal changes, no refactoring |
| [refactor-task.md](ai/tasks/refactor-task.md) | Improving structure — no logic changes |
| [new-feature-task.md](ai/tasks/new-feature-task.md) | Adding new functionality — clean encapsulation |
| [qgis-processing-task.md](ai/tasks/qgis-processing-task.md) | Working with QGIS Processing algorithms |
