# MST Module Architecture

Status: Monolithic — refactoring planned.

## Current State

`CreateMST.py` is a monolithic 372-line function:

- Single large `calculate_mst()` function with embedded helper functions
- Delaunay triangulation, street processing, and MST calculation all in one place
- Complex nested operations with no clear separation of concerns
- Constants defined inline (`road_length=50`, `buffer_distance=5`, `coordinate_tolerance=0.0001`)

## Target Architecture

```
ibtool/ibtool_tools/mst/     # Modular target structure
├── __init__.py
├── delaunay_processor.py    # Delaunay triangulation operations
├── street_processor.py     # Street filtering and node detection
├── mst_calculator.py       # Graph operations and MST calculation
├── mst_data_classes.py     # Data structures for MST processing
└── create_mst.py           # Orchestrator class
```

## Design Principles for Refactoring

- Each processor owns its business logic parameters as class constants
- No shared config objects — simple constructors without parameters
- QGIS technical parameters centralized in `helpers/qgis_defaults.py`
- Clear separation: geometry vs. streets vs. graph algorithms
- Backward compatibility through simple wrapper functions

## Algorithm Overview

1. **Delaunay triangulation**: Creates a connection network between building centroids
2. **Street processing**: Filters short street segments, detects nodes
3. **Graph construction**: Builds a weighted graph from Delaunay edges
4. **MST calculation**: Computes the minimum spanning tree (Kruskal/Prim)
5. **Edge filtering**: Removes edges that cross streets
