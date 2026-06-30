# ibtool_tools Module Structure Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every module under `ibtool_tools/` the same four-section structure as `GapClose.py`: module docstring with Public API listing, `_DEBUG_TOOL_NAME`, module-level constants, private helpers, public API.

**Architecture:** Pure structural refactoring — no logic changes. Changes are: new/expanded module docstrings, new section-header comments, one `_DEBUG_TOOL_NAME` constant per file, extraction of one nested function (`select_block → _select_block`), extraction of four magic defaults to named constants in `PatchRemove.py`.

**Tech Stack:** Python 3.11, QGIS 3.40 — no new dependencies.

---

## Files Modified

| File | Change type |
|---|---|
| `ibtool_tools/AddSingleBuilding.py` | docstring + Public API header |
| `ibtool_tools/Blocker.py` | docstring + section headers |
| `ibtool_tools/EdgeCatch.py` | docstring + `_DEBUG_TOOL_NAME` + import fix |
| `ibtool_tools/FootprintDensity.py` | docstring + `_DEBUG_TOOL_NAME` + extract `_select_block` + headers |
| `ibtool_tools/HoleClose.py` | docstring + `_DEBUG_TOOL_NAME` + constants header |
| `ibtool_tools/ImportFilter.py` | docstring Public API block + section headers |
| `ibtool_tools/ErodeEmptyAreas.py` | docstring reformatted |
| `ibtool_tools/PatchRemove.py` | docstring + `DEFAULT_*` constants + Public API header |
| `ibtool_tools/MST_Clustering.py` | docstring + section headers |
| `ibtool_tools/CreateMST.py` | docstring + `_DEBUG_TOOL_NAME` + Public API header |

---

### Task 1: AddSingleBuilding.py — docstring + Public API header

**Files:**
- Modify: `ibtool_tools/AddSingleBuilding.py:1`

- [ ] **Step 1: Replace the single-line module docstring with the multi-line version**

Replace lines 1–1:
```python
"""AddSingleBuilding: Filter large isolated buildings and convert them to bounding rectangles."""
```
with:
```python
# -*- coding: utf-8 -*-
"""Add single large isolated buildings to the settlement cluster layer.

Identifies buildings whose centroid lies outside existing cluster polygons
and whose area exceeds a configurable threshold, then converts each such
building to its oriented bounding rectangle.

Public API
----------
add_single_bdg(input_hu, rect_merge, crs, workspace_path, threshold, debug_mode)
"""
```

- [ ] **Step 2: Add Public API section header before `add_single_bdg`**

Add before `def add_single_bdg(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 3: Run tests**

```
pytest test/ -v
```
Expected: all tests that ran before still pass.

- [ ] **Step 4: Commit**

```
git add ibtool_tools/AddSingleBuilding.py
git commit -m "refactor: add module docstring and Public API header to AddSingleBuilding"
```

---

### Task 2: Blocker.py — docstring + section headers

**Files:**
- Modify: `ibtool_tools/Blocker.py:1`

- [ ] **Step 1: Replace single-line docstring**

Replace line 1:
```python
"""Blocker: Create city block polygons from a road network and partition boundary."""
```
with:
```python
# -*- coding: utf-8 -*-
"""Create city block polygons from a road network and partition boundary.

Polygonizes the merged road network and partition outline, removes blocks
that contain no building footprints, and annotates each remaining block
with a unique NAME attribute.

Public API
----------
blocker(road_network, hu_input, partition, debug_mode, workspace_path)
"""
```

- [ ] **Step 2: Add Private helpers header before `_build_block_polygons`**

Add before `def _build_block_polygons(`:
```python

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

```

- [ ] **Step 3: Add Public API header before `blocker`**

Add before `def blocker(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 4: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/Blocker.py
git commit -m "refactor: add module docstring and section headers to Blocker"
```

---

### Task 3: EdgeCatch.py — docstring + `_DEBUG_TOOL_NAME` + import fix

**Files:**
- Modify: `ibtool_tools/EdgeCatch.py`

- [ ] **Step 1: Replace module docstring**

Replace lines 1–9:
```python
"""EdgeCatch — snaps grouped building polygons to the road network.

For each building group, orthogonal projection lines are drawn from the building
outline to the adjacent road segments.  The combined line geometry is polygonized
and the result is clipped to the relevant city block, producing road-aligned
settlement boundaries.

Private helpers and algorithm constants live in helpers/edge_catch_utils.py.
"""
```
with:
```python
# -*- coding: utf-8 -*-
"""Snap grouped building polygons to the road network.

For each building group, orthogonal projection lines are drawn from the building
outline to the adjacent road segments. The combined line geometry is polygonized
and the result is clipped to the relevant city block, producing road-aligned
settlement boundaries.

Private helpers and algorithm constants live in helpers/edge_catch_utils.py.

Public API
----------
edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs, workspace_path,
           debug_mode)
"""
```

- [ ] **Step 2: Remove `DEBUG_TOOL_NAME` from the edge_catch_utils import**

Change:
```python
from ..helpers.edge_catch_utils import (
    filter_roads_near_buildings,
    process_single_feature,
    ROAD_SEGMENT_LENGTH,
    ROAD_BUFFER_DISTANCE,
    DEBUG_TOOL_NAME,
)
```
to:
```python
from ..helpers.edge_catch_utils import (
    filter_roads_near_buildings,
    process_single_feature,
    ROAD_SEGMENT_LENGTH,
    ROAD_BUFFER_DISTANCE,
)
```

- [ ] **Step 3: Add `_DEBUG_TOOL_NAME` block after imports**

Add after all imports:
```python

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "05_EdgeCatch"
```

- [ ] **Step 4: Update the `save_debug_layer` call to use `_DEBUG_TOOL_NAME`**

Change:
```python
    if debug_mode and workspace_path:
        save_debug_layer(polygons_merge, DEBUG_TOOL_NAME, "polygons_merged", workspace_path)
```
to:
```python
    if debug_mode and workspace_path:
        save_debug_layer(polygons_merge, _DEBUG_TOOL_NAME, "polygons_merged", workspace_path)
```

- [ ] **Step 5: Add Public API header before `edge_catch`**

Add before `def edge_catch(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 6: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/EdgeCatch.py
git commit -m "refactor: add module docstring, _DEBUG_TOOL_NAME, and Public API header to EdgeCatch"
```

---

### Task 4: HoleClose.py — docstring + `_DEBUG_TOOL_NAME` + constants header

**Files:**
- Modify: `ibtool_tools/HoleClose.py`

- [ ] **Step 1: Add encoding line and module docstring at top**

Replace the start of the file (before the first import) with:
```python
# -*- coding: utf-8 -*-
"""Close interior holes in settlement polygon layers up to a maximum hole area.

Dissolves the input, converts to boundary lines, polygonizes, identifies inner
holes, filters by area, and merges small holes back into the dissolved polygon.

Public API
----------
hole_close(input_layer, max_hole_size)
"""
from qgis.core import QgsProcessing, QgsVectorLayer
from qgis import processing

from ..helpers.geometry_utils import shp_area2, get_hole_polygons

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "HoleClose"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# QGIS extractbyattribute operator: area <= threshold (less than or equal)
_OPERATOR_LESS_THAN_OR_EQUAL: int = 5
"""QGIS extractbyattribute operator code for ``<= threshold`` comparisons."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 2: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/HoleClose.py
git commit -m "refactor: add module docstring, _DEBUG_TOOL_NAME, and section headers to HoleClose"
```

---

### Task 5: ImportFilter.py — Public API block + section headers

**Files:**
- Modify: `ibtool_tools/ImportFilter.py:1`

- [ ] **Step 1: Expand the existing module docstring**

Replace line 1:
```python
"""Import filter for building footprints based on ATKIS function codes and density analysis."""
```
with:
```python
# -*- coding: utf-8 -*-
"""Import filter for building footprints based on ATKIS function codes and density analysis.

Reads a filter definition file to build positive and negative QGIS selection
expressions, then applies a multi-step filter pipeline (function type, kernel
density, minimum area) to the input building layer.

Public API
----------
import_filter(filename, hu_layer)
input_hu_filter(hu_layer, filter_file, min_area, cell_size, neighborhood_radius,
                debug_mode, workspace_path)
"""
```

- [ ] **Step 2: Add Private helpers header before `_create_filter_string`**

Add before `def _create_filter_string(`:
```python

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

```

- [ ] **Step 3: Add Public API header before `import_filter`**

Add before `def import_filter(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 4: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/ImportFilter.py
git commit -m "refactor: add Public API block and section headers to ImportFilter"
```

---

### Task 6: ErodeEmptyAreas.py — reformulate module docstring

**Files:**
- Modify: `ibtool_tools/ErodeEmptyAreas.py:1-27`

- [ ] **Step 1: Replace docstring (lines 2–26)**

The current docstring lists every constant inline. Replace the entire multi-line docstring block with:
```python
# -*- coding: utf-8 -*-
"""Remove building-free voids from settlement polygons.

For each settlement polygon, building footprints are buffered by
``clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)`` metres. Areas
inside the settlement that lie outside all building buffers are treated as
building-free voids. Only voids where less than
``BOUNDARY_CONTACT_THRESHOLD_PCT`` percent of their boundary coincides with
the settlement outer boundary are removed; voids with equal or higher contact
are kept.

Public API
----------
erode_empty_areas(input_layer, buildings_layer, min_empty_area, min_buffer_m,
                  max_buffer_m, contact_threshold_pct, workspace_path, debug_mode)
"""
```
(The constants themselves stay in the Module-level constants section below the imports — no change needed there.)

- [ ] **Step 2: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/ErodeEmptyAreas.py
git commit -m "refactor: reformulate ErodeEmptyAreas module docstring to GapClose.py style"
```

---

### Task 7: MST_Clustering.py — docstring + section headers

**Files:**
- Modify: `ibtool_tools/MST_Clustering.py`

- [ ] **Step 1: Add encoding line and module docstring at top of file**

Insert before the first import:
```python
# -*- coding: utf-8 -*-
"""MST-based clustering of building footprints into oriented bounding rectangles.

Iterates over MST edges sorted by weight and merges pairs of building polygons
into clusters when the ratio of their combined footprint area to the oriented
bounding rectangle area exceeds a configurable overlap ratio. Each resulting
cluster is represented as an oriented bounding rectangle.

Public API
----------
calc_bounding_rect(hu_polyline, hu_layer, mode, crs)
mst_clustering(hu_layer, mst_layer, crs, overlap_ratio, debug_mode, workspace_path)
"""
```

- [ ] **Step 2: Add Private helpers header before `_main_angle`**

Add before `def _main_angle(`:
```python

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

```

- [ ] **Step 3: Add Public API header before `calc_bounding_rect`**

Add before `def calc_bounding_rect(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 4: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/MST_Clustering.py
git commit -m "refactor: add module docstring and section headers to MST_Clustering"
```

---

### Task 8: CreateMST.py — docstring + `_DEBUG_TOOL_NAME` + Public API header

**Files:**
- Modify: `ibtool_tools/CreateMST.py`

- [ ] **Step 1: Add encoding line and module docstring at top of file**

Insert before the first import:
```python
# -*- coding: utf-8 -*-
"""Minimum Spanning Tree (MST) calculation orchestrator.

Coordinates Delaunay triangulation, street-based edge filtering, and MST
calculation to produce a line layer connecting building centroids via the
minimum spanning tree of the triangulated graph.

Public API
----------
CreateMST                              — orchestrator class
calculate_mst(input_bdg, streets_orig, spatial_reference)
"""
```

- [ ] **Step 2: Add `_DEBUG_TOOL_NAME` block after imports**

Add after all imports (after `from ..helpers.logger import Logger`):
```python

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "CreateMST"
```

- [ ] **Step 3: Add Public API header before `class CreateMST`**

Add before `class CreateMST:`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 4: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/CreateMST.py
git commit -m "refactor: add module docstring, _DEBUG_TOOL_NAME, and Public API header to CreateMST"
```

---

### Task 9: PatchRemove.py — docstring + `DEFAULT_*` constants + Public API header

**Files:**
- Modify: `ibtool_tools/PatchRemove.py`

- [ ] **Step 1: Add encoding line and module docstring at top of file**

Insert before the first import:
```python
# -*- coding: utf-8 -*-
"""Remove settlement patches that are too small or contain too few buildings.

Converts multipart input to singlepart, counts intersecting buildings per
patch, and filters out patches below configurable size and building-count
thresholds. Dense blocks identified by identify_dense_blocks are always
retained regardless of patch size.

Public API
----------
patch_remove(input_poly, input_bdg, crs, workspace_path, min_patch_size,
             min_bdg_count, footprint_area_sum, footprint_density_threshold,
             debug_mode)
"""
```

- [ ] **Step 2: Add Module-level constants block after `_DEBUG_TOOL_NAME`**

After the existing `_DEBUG_TOOL_NAME = "08_PatchRemove"` block, add:
```python

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_PATCH_SIZE = 10_000
"""Minimum patch area (m²) below which a settlement polygon is discarded."""

DEFAULT_MIN_BDG_COUNT = 20
"""Minimum number of buildings a patch must contain to be retained."""

DEFAULT_FOOTPRINT_AREA_SUM = 6_000
"""Minimum total footprint area (m²) for a dense block to be retained unconditionally."""

DEFAULT_FOOTPRINT_DENSITY_THRESHOLD = 18
"""Footprint density threshold (%) passed to identify_dense_blocks."""
```

- [ ] **Step 3: Update `patch_remove` signature to use the new constants as defaults**

Change:
```python
def patch_remove(
    input_poly: QgsVectorLayer,
    input_bdg: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    workspace_path: str,
    min_patch_size: int = 10000,
    min_bdg_count: int = 20,
    footprint_area_sum: int = 6000,
    footprint_density_threshold: int = 18,
    debug_mode: bool = False,
) -> QgsVectorLayer:
```
to:
```python
def patch_remove(
    input_poly: QgsVectorLayer,
    input_bdg: QgsVectorLayer,
    crs: QgsCoordinateReferenceSystem,
    workspace_path: str,
    min_patch_size: int = DEFAULT_MIN_PATCH_SIZE,
    min_bdg_count: int = DEFAULT_MIN_BDG_COUNT,
    footprint_area_sum: int = DEFAULT_FOOTPRINT_AREA_SUM,
    footprint_density_threshold: int = DEFAULT_FOOTPRINT_DENSITY_THRESHOLD,
    debug_mode: bool = False,
) -> QgsVectorLayer:
```

- [ ] **Step 4: Add Public API header before `patch_remove`**

Add before `def patch_remove(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 5: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/PatchRemove.py
git commit -m "refactor: add module docstring, DEFAULT_* constants, and Public API header to PatchRemove"
```

---

### Task 10: FootprintDensity.py — docstring + `_DEBUG_TOOL_NAME` + extract `_select_block`

**Files:**
- Modify: `ibtool_tools/FootprintDensity.py`

- [ ] **Step 1: Add encoding line and module docstring**

Insert before the first import:
```python
# -*- coding: utf-8 -*-
"""Building footprint density calculations for city blocks.

Provides tools to compute the overlap ratio of building footprints within
city blocks, identify dense settlement blocks, and derive a global footprint
density threshold for the processing pipeline.

Public API
----------
calc_footprint_density(InputBdg, InputStrNetwork, Buffer, GlobalThreshold, Ext,
                       MinBdgCount, Partition)
footprint_density(HU_Input, Bloecke, footprint_density_threshold)
identify_dense_blocks(HU_Input, Bloecke, footprintdensitythreshold)
"""
```

- [ ] **Step 2: Add `_DEBUG_TOOL_NAME` block after imports**

After all imports (after the `try/except ImportError` block), add:
```python

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "FootprintDensity"
```

- [ ] **Step 3: Extract `select_block` as top-level `_select_block`**

Remove the nested `def select_block(InputStrNetwork, InputBdg, Buffer):` from inside
`calc_footprint_density` and add the following top-level function before
`calc_footprint_density`, with `min_bdg_count` added as an explicit parameter:

```python
# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _select_block(InputStrNetwork, InputBdg, Buffer, min_bdg_count):
    """Select city blocks that intersect buildings and contain enough of them.

    Polygonizes the street network, selects blocks that intersect the buffered
    building outline (excluding boundary-touching blocks), and returns only
    blocks that contain at least ``min_bdg_count`` buildings.

    Args:
        InputStrNetwork: Road network polyline layer (QgsVectorLayer).
        InputBdg: Building footprint polygon layer (QgsVectorLayer).
        Buffer: Buffer distance (m) around buildings to define the settlement extent.
        min_bdg_count: Minimum number of buildings a block must contain to be kept.

    Returns:
        QgsVectorLayer of filtered city blocks with a building-count join field.
    """
    # Convert the street network to polygons
    InputStrNetwork_Poly = processing.run("native:polygonize", {
        'INPUT': InputStrNetwork,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    # Create a spatial index for the polygonized street network
    processing.run("native:createspatialindex", {
        'INPUT': InputStrNetwork_Poly
    })

    # Buffer buildings and dissolve them
    InputBdg_Buff = processing.run("native:buffer", {
        'INPUT': InputBdg,
        'DISTANCE': Buffer,
        'SEGMENTS': 5,
        'END_CAP_STYLE': 0,
        'JOIN_STYLE': 0,
        'MITER_LIMIT': 2,
        'DISSOLVE': True,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    processing.run("native:createspatialindex", {
        'INPUT': InputBdg_Buff
    })

    InputBdg_Buff_Line = processing.run("native:polygonstolines", {
        'INPUT': InputBdg_Buff,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    # First selection: blocks intersecting the building buffer outline
    processing.run("native:selectbylocation", {
        'INPUT': InputStrNetwork_Poly,
        'PREDICATE': [0],
        'INTERSECT': InputBdg_Buff_Line,
        'METHOD': 0
    })

    selected_ids = InputStrNetwork_Poly.selectedFeatureIds()
    all_ids = [f.id() for f in InputStrNetwork_Poly.getFeatures()]
    inverted_ids = [fid for fid in all_ids if fid not in selected_ids]
    InputStrNetwork_Poly.selectByIds(inverted_ids)

    InputStrNetwork_Poly_Sel = processing.run(
        "native:saveselectedfeatures",
        {'INPUT': InputStrNetwork_Poly, 'OUTPUT': 'TEMPORARY_OUTPUT'}
    )['OUTPUT']

    # Second selection: blocks that also intersect buildings
    BlocksInside = processing.run("native:selectbylocation", {
        'INPUT': InputStrNetwork_Poly_Sel,
        'PREDICATE': [0],
        'INTERSECT': InputBdg,
        'METHOD': 2
    })['OUTPUT']

    # Spatial join: count buildings per block
    Blocks_join = processing.run("native:joinbylocationsummary", {
        'INPUT': BlocksInside,
        'JOIN': InputBdg,
        'PREDICATE': [0],
        'JOIN_FIELDS': [],
        'SUMMARIES': [0],
        'DISCARD_NONMATCHING': False,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    count_field = None
    for field in Blocks_join.fields():
        if field.name().endswith('_count'):
            count_field = field.name()
            break

    if not count_field:
        msg("ERROR: Could not find count field in joined layer", 'CRITICAL')
        raise ValueError("Count field not found after spatial join")

    Blocks_filtered = processing.run("native:extractbyattribute", {
        'INPUT': Blocks_join,
        'FIELD': count_field,
        'OPERATOR': 2,
        'VALUE': min_bdg_count,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    return Blocks_filtered
```

- [ ] **Step 4: Update `calc_footprint_density` to call `_select_block` instead of nested `select_block`**

In `calc_footprint_density`, remove the `def select_block(...)` nested function definition entirely.

Change all three call sites:
```python
Inner_BlocksPart = select_block(SelStrassen, SelHU, Buffer)
```
to:
```python
Inner_BlocksPart = _select_block(SelStrassen, SelHU, Buffer, MinBdgCount)
```

and:
```python
Inner_Blocks = select_block(InputStrNetwork, InputBdg, Buffer)
```
to:
```python
Inner_Blocks = _select_block(InputStrNetwork, InputBdg, Buffer, MinBdgCount)
```

- [ ] **Step 5: Add Public API header before `calc_footprint_density`**

Add before `def calc_footprint_density(`:
```python

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

```

- [ ] **Step 6: Run tests and commit**

```
pytest test/ -v
git add ibtool_tools/FootprintDensity.py
git commit -m "refactor: add module docstring, _DEBUG_TOOL_NAME, extract _select_block in FootprintDensity"
```
