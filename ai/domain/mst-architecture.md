# MST Module Architecture

Status: **Split complete** (Phase 12 done).

## Current Structure

```
ibtool_tools/
├── CreateMST.py             # Orchestrator class + backward-compat calculate_mst()
└── mst/
    ├── __init__.py          # Re-exports all public symbols
    ├── delaunay_processor.py  # Delaunay triangulation operations
    ├── street_processor.py    # Street filtering and node detection
    ├── mst_calculator.py      # Graph operations and MST calculation
    └── mst_data_classes.py    # Data structures for MST processing
```

`CreateMST.py` is the orchestrator; it imports all processors from the `mst/` subpackage.
The module-level `calculate_mst()` function is a thin backward-compatible wrapper.

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
