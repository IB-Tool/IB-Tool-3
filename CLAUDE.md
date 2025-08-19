# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**IBTool** is a QGIS plugin for settlement delineation based on building footprints. It provides automated geospatial processing tools for urban planning and settlement analysis, implementing complex algorithms for clustering, density calculations, and minimum spanning tree (MST) analysis.

## Architecture

### Core Components

- **`ibtool.py`**: Main plugin class and entry point
- **`ibtool_dialog.py`**: User interface dialog implementation
- **`ibtool_cli.py`**: Command-line interface version with direct imports
- **`helpers/`**: Utility modules for common functionality
  - `logger.py`: Comprehensive logging system (UI, file, QGIS messages)
  - `data_loader.py`: Geodata loading and validation
  - `geometry_utils.py`: Spatial geometry operations
  - `system_utils.py`: System path and environment utilities
  - `message.py`: User messaging system
  - `qgis_defaults.py`: Global QGIS standard parameters for consistent tool behavior
- **`ibtool_tools/`**: Core processing algorithms
  - `Blocker.py`: Settlement blocking and partitioning
  - `CreateMST.py`: Minimum spanning tree creation (refactored, modular architecture)
  - `mst/`: Modular MST components (delaunay_processor, street_processor, mst_calculator, mst_data_classes)
  - `MST_Clustering.py`: MST-based clustering algorithms
  - `FootprintDensity.py`: Building density calculations
  - `ImportFilter.py`: Data filtering and preprocessing
  - `GapClose.py`, `HoleClose.py`: Geometry gap/hole closing
  - `EdgeCatch.py`: Edge detection algorithms
  - `AddSingleBuilding.py`: Single building processing
  - `PatchRemove.py`: Patch removal operations

### Data Flow

The plugin processes multiple geodata layers (HU=buildings, RN=roads, Part=partitioning zones, Aux=auxiliary layers) through a pipeline of geometric analysis tools to generate settlement boundaries and density maps stored as GeoPackage files.

### MST Module Architecture (Reference Implementation)

The `ibtool_tools/mst/` module demonstrates the preferred modular architecture:

**Core Classes:**
- `DelaunayProcessor`: Handles Delaunay triangulation and geometric operations
- `StreetProcessor`: Manages street data processing and filtering (ROAD_LENGTH_THRESHOLD=50.0, BUFFER_DISTANCE=5.0)
- `MSTCalculator`: Performs MST calculations and graph operations (COORDINATE_TOLERANCE=0.0001)
- `CreateMST`: Orchestrates the complete workflow, coordinates all processors

**Data Classes:**
- `mst_data_classes.py`: Defines EdgeData, MSTResult, TriangulationResult, StreetProcessingResult, BuildingCentroidsResult

**Design Principles Applied:**
- Each processor owns its business logic parameters as class constants
- No shared config objects - simple constructors with no parameters
- QGIS technical parameters are centralized in `helpers/qgis_defaults.py`
- Clean separation of concerns: geometry vs. streets vs. graph algorithms
- Backward compatibility maintained through simple wrapper functions

## Common Development Commands

### Testing
```bash
# Run all tests using pytest in Docker environment
docker build -t qgis-plugin-test .
docker run --rm qgis-plugin-test

# Run tests locally (requires QGIS environment setup)
pytest test/

# Run specific test
pytest test/test_blocker.py -v

# Run with coverage
pytest test/ --cov=. --cov-report=html
```

### Building and Deployment
```bash
# Compile UI and resources (Windows)
compile.bat

# Compile using pb_tool (cross-platform)
pb_tool compile
pb_tool deploy

# Using Makefile (Linux/Mac)
make compile
make test
make deploy
```

### Translation Management
```bash
# Update translation strings
make transup

# Compile translations
make transcompile

# Clean compiled translations
make transclean
```

### Code Quality
```bash
# PEP8 style checking
make pep8

# PyLint analysis
make pylint
```

## Development Environment Setup

### Prerequisites
- QGIS 3.40-3.50
- Python 3.9+ (3.11 recommended)
- Required Python packages: numpy, scipy, sklearn, networkx, pandas, matplotlib, geopandas, shapely

### Docker Development
The project includes a complete Docker-based CI/CD pipeline using the official QGIS base image:

```bash
# Build development environment
docker build -t qgis-plugin-dev .

# Run interactive development session
docker run --rm -it -v $(pwd):/app qgis-plugin-dev /bin/bash

# Run tests with coverage
docker run --rm -v $(pwd):/app qgis-plugin-dev
```

### Local QGIS Setup
The plugin auto-detects QGIS installations or uses `QGIS_PREFIX_PATH` environment variable. For custom installations:

```bash
export QGIS_PREFIX_PATH=/path/to/qgis
```

## Plugin Installation Paths
- Windows: `C:\Users\<User>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
- macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`

## Code Conventions

- Follow PEP8 coding standards with type annotations
- Use Google-style docstrings for all functions and classes
- Write comprehensive tests for new functionality using pytest
- All user-facing strings should be translatable (use QCoreApplication.translate)
- Keep functions focused and modular
- Use the project's logging system for all output (not print statements)

## Developer Preferences and Architecture Guidelines

### Parameter Management (Learned from MST Refactoring)
- **Avoid over-engineering configurations**: Only create separate config files when parameters are shared across multiple modules
- **Local parameters belong locally**: Business logic parameters should be class constants where they're used
- **YAGNI principle**: Don't create abstractions until they're actually needed (2-3 parameters don't justify a config class)
- **Use helpers/qgis_defaults.py**: For technical QGIS parameters (buffer settings, precision) that should be consistent across tools
- **Single Source of Truth**: Each parameter should be defined in exactly one place

### Class Design Preferences
- **Favor composition over inheritance**: Use specialized classes that work together rather than complex inheritance hierarchies  
- **Clear responsibilities**: Each class should have one clear purpose (DelaunayProcessor, StreetProcessor, etc.)
- **Minimal constructors**: Avoid passing config objects unless truly necessary - prefer simple initialization
- **Constants as class attributes**: Use `CLASS_CONSTANT = value` for parameters used only within that class

### Code Organization
- **Modular architecture**: Break large functions (500+ lines) into specialized classes with focused methods
- **No magic numbers**: All numeric constants should be named and documented
- **Eliminate redundancy**: If a parameter appears in multiple places, question if it's really shared or just duplicated
- **Pragmatic refactoring**: Always ask "does this complexity serve a real purpose?" before adding abstractions

### Testing and Maintenance
- **Test individual components**: Modular design enables testing of isolated functionality
- **Keep APIs simple**: Complex parameter passing makes code harder to understand and test
- **Document business logic**: Parameters that affect algorithm behavior need clear documentation
- **Prefer explicit over implicit**: `StreetProcessor.ROAD_LENGTH_THRESHOLD` is clearer than `config.road_length_threshold`

### File Organization
- **Group related functionality**: Use module directories (like `mst/`) for complex algorithms
- **Global utilities in helpers/**: Technical parameters, logging, geometry utils belong in helpers/
- **Avoid config proliferation**: Resist creating multiple config files for different purposes

### Usage Patterns

**For QGIS Operations:**
```python
from helpers.qgis_defaults import QGISDefaults

qgis_defaults = QGISDefaults()
buffer_result = processing.run("native:buffer", {
    'SEGMENTS': qgis_defaults.buffer_segments,
    'END_CAP_STYLE': qgis_defaults.buffer_end_cap_style,
    # ... other QGIS parameters
})
```

**For Algorithm-Specific Parameters:**
```python
class StreetProcessor:
    ROAD_LENGTH_THRESHOLD = 50.0  # Business logic parameter
    
    def filter_short_streets(self, streets):
        expression = f'"length" < {self.ROAD_LENGTH_THRESHOLD}'
```

**For Modular Processing:**
```python
# Simple initialization - no config objects needed
processor = StreetProcessor()
calculator = MSTCalculator() 
delaunay = DelaunayProcessor()

# Clean workflow orchestration
mst_creator = CreateMST()
result = mst_creator.calculate_mst(buildings, streets, crs)
```

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:
1. Builds Docker image with QGIS 3.40 environment
2. Installs all Python dependencies
3. Runs pytest test suite with coverage
4. Uploads coverage reports to Codecov

## Logging System

The plugin features a multi-output logging system:
- **Log Levels**: CRITICAL, WARNING, INFO, SUCCESS (configurable via UI)
- **Output Destinations**: UI message window, log files (`logs/logfile_YYYY-MM-DD_HH-MM-SS.txt`), QGIS message bar
- **Configuration**: Log level and directory selectable through plugin interface

## Input Data Requirements

The plugin expects specific layer types:
- **HU**: Building footprint polygons
- **RN**: Road network linestrings  
- **Part**: Partitioning/zoning polygons
- **Aux**: Auxiliary analysis layers
- **Filter File**: Text file with positive/negative filtering criteria

All input layers must use the same coordinate reference system (CRS).

## Testing Strategy

- **Unit Tests**: Individual component testing (`test/test_*.py`)
- **Integration Tests**: Full workflow testing (`tests/integration/`)
- **GUI Tests**: Dialog and interface testing (headless mode via xvfb)
- **Docker Testing**: Consistent environment using QGIS Docker image
- **Coverage**: Comprehensive test coverage with reporting

## Key Configuration Files

- **`metadata.txt`**: Plugin metadata for QGIS plugin repository
- **`pb_tool.cfg`**: Plugin Builder tool configuration
- **`Dockerfile`**: Containerized test environment setup
- **`Makefile`**: Build automation and development tasks
- **`compile.bat`**: Windows compilation script
- **`.github/workflows/ci.yml`**: Continuous integration pipeline

## Important Notes

- Never add dependencies without prior consultation
- Keep processing algorithms stateless and testable
- Use the centralized logging system for all output
- All changes should include appropriate tests
- Update `CHANGELOG.md` for significant changes
- Maintain German translation files in `i18n/`