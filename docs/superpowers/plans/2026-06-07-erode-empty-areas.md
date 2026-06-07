# ErodeEmptyAreas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ErodeEmptyAreas` as the final per-partition pipeline step, removing voids (≥ 500 m²) within settlement polygons that contain no building footprints.

**Architecture:** New module `ibtool_tools/ErodeEmptyAreas.py` with one public function `erode_empty_areas(input_layer, buildings_layer, ...)`. Per-building buffer distance scales as `clamp(sqrt(area), 10, 100)` m. Called in `_run_partition_pipeline` after `patch_remove`. Unit tests cover all three early-return branches (no Processing required).

**Tech Stack:** Python 3.11, QGIS 3.40+, `qgis.core.QgsVectorLayer`, `safe_processing_run`, `save_debug_layer`, `Logger`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| **Write** | `ibtool_tools/ErodeEmptyAreas.py` | Module: constants, `_build_buffer_layer`, `erode_empty_areas` |
| **Write** | `test/test_erode_empty_areas.py` | Unit tests for early-return branches |
| **Modify** | `ibtool/ibtool.py:73,1218-1220` | Add import + call after `patch_remove` |
| **Write** | `ai/domain/erode-empty-areas.md` | Domain knowledge doc |
| **Modify** | `docs/how-it-works.md:46-53` | Add Step 10 to pipeline diagram and step list |

---

## Task 1 — Unit Tests (failing)

**Files:**
- Write: `test/test_erode_empty_areas.py`

- [ ] **Step 1.1: Write the test file**

```python
# test/test_erode_empty_areas.py
"""
Tests for ibtool_tools/ErodeEmptyAreas.py.

The module exposes one public function:

  erode_empty_areas(input_layer, buildings_layer,
                    min_empty_area=500.0, min_buffer_m=10.0, max_buffer_m=100.0,
                    workspace_path=None, debug_mode=False)

Buffer scaling formula:
  buf_dist = clamp(sqrt(building_area), min_buffer_m, max_buffer_m)

Unit tests cover (no Processing — early return branches):
  - empty input layer → returns input unchanged
  - invalid input layer → returns input unchanged
  - empty buildings layer → returns input unchanged
"""

import pytest
from qgis.core import QgsVectorLayer

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas


class TestErodeEmptyAreasEarlyReturn:
    """Unit tests for erode_empty_areas early-return branches (no Processing)."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_input_returns_input_unchanged(self):
        """erode_empty_areas on a valid but empty settlement layer returns input unchanged."""
        settlement = make_polygon_layer()   # 0 features
        buildings = make_polygon_layer()
        add_feature_to_layer(buildings, make_square_geom(0, 0, 10))

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_invalid_input_layer_returns_early(self):
        """erode_empty_areas on an uninitialised QgsVectorLayer returns without crash."""
        invalid_layer = QgsVectorLayer()    # uninitialised
        buildings = make_polygon_layer()
        add_feature_to_layer(buildings, make_square_geom(0, 0, 10))

        result = erode_empty_areas(invalid_layer, buildings)

        assert result is not None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_buildings_returns_settlement_unchanged(self):
        """erode_empty_areas with 0 buildings returns the settlement layer unchanged."""
        settlement = make_polygon_layer()
        add_feature_to_layer(settlement, make_square_geom(0, 0, 100))
        buildings = make_polygon_layer()   # 0 features

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() > 0   # settlement returned as-is
```

- [ ] **Step 1.2: Run tests — confirm ImportError (module does not exist yet)**

```
pytest test/test_erode_empty_areas.py -v -m unit
```

Expected: `ImportError: cannot import name 'erode_empty_areas'` or `ModuleNotFoundError`

---

## Task 2 — Implement `ErodeEmptyAreas.py`

**Files:**
- Write: `ibtool_tools/ErodeEmptyAreas.py`

- [ ] **Step 2.1: Write the module**

Replace the current empty `ibtool_tools/ErodeEmptyAreas.py` with:

```python
# -*- coding: utf-8 -*-
"""Remove building-free voids from settlement polygons.

For each settlement polygon, building footprints within the boundary are
selected and buffered by ``clamp(sqrt(building_area), MIN_BUFFER_M, MAX_BUFFER_M)``
metres. Areas inside the settlement that lie outside all building buffers are
treated as building-free voids and subtracted from the settlement.

Constants:
    _DEBUG_TOOL_NAME: Folder-name prefix for debug layer output, reflecting
        the call order in the main processing pipeline (``"09_ErodeEmptyAreas"``).
    MIN_BUFFER_M: Minimum per-building buffer distance in metres (10.0).
    MAX_BUFFER_M: Maximum per-building buffer distance in metres (100.0).
    MIN_EMPTY_AREA_M2: Minimum area (m²) of a building-free void to remove (500.0).
    TOPOLOGY_GRID_SIZE: Grid size for difference operations (0.00001).
"""

import math

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsProcessing,
)

from ..helpers.logger import Logger
from ..helpers.debug_utils import save_debug_layer
from ..helpers.safe_processing import safe_processing_run

# ---------------------------------------------------------------------------
# Debug folder name — prefix reflects call order in the main pipeline
# ---------------------------------------------------------------------------
_DEBUG_TOOL_NAME = "09_ErodeEmptyAreas"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MIN_BUFFER_M = 10.0
"""Minimum per-building buffer distance (m). Applies to buildings with area ≤ 100 m²."""

MAX_BUFFER_M = 100.0
"""Maximum per-building buffer distance (m). Applies to buildings with area ≥ 10 000 m²."""

MIN_EMPTY_AREA_M2 = 500.0
"""Minimum area (m²) of a building-free void to remove. Smaller voids are kept."""

TOPOLOGY_GRID_SIZE = 0.00001
"""Grid size for difference operations (topology snapping)."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_buffer_layer(sel_buildings, min_buffer_m, max_buffer_m):
    """Build a memory layer of per-building buffer polygons.

    Buffer distance per building: ``clamp(sqrt(area), min_buffer_m, max_buffer_m)``.

    Args:
        sel_buildings: QgsVectorLayer of building footprints.
        min_buffer_m: Minimum buffer distance in metres.
        max_buffer_m: Maximum buffer distance in metres.

    Returns:
        QgsVectorLayer (memory, Polygon) with one buffer feature per building.
        May have 0 features if all building geometries are null/empty.
    """
    crs = sel_buildings.crs()
    mem_uri = f"Polygon?crs={crs.authid()}"
    buf_layer = QgsVectorLayer(mem_uri, "building_buffers", "memory")
    provider = buf_layer.dataProvider()
    buf_layer.updateFields()

    buf_feats = []
    for feat in sel_buildings.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isNull() or geom.isEmpty():
            continue
        area = geom.area()
        buf_dist = max(min_buffer_m, min(max_buffer_m, math.sqrt(area)))
        buf_geom = geom.buffer(buf_dist, 5)
        if buf_geom and not buf_geom.isEmpty():
            f = QgsFeature()
            f.setGeometry(buf_geom)
            buf_feats.append(f)

    provider.addFeatures(buf_feats)
    return buf_layer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def erode_empty_areas(input_layer, buildings_layer,
                      min_empty_area=MIN_EMPTY_AREA_M2,
                      min_buffer_m=MIN_BUFFER_M,
                      max_buffer_m=MAX_BUFFER_M,
                      workspace_path=None,
                      debug_mode=False):
    """Remove building-free voids from a settlement polygon.

    Selects building footprints within ``input_layer``, buffers each by
    ``clamp(sqrt(building_area), min_buffer_m, max_buffer_m)`` metres,
    then subtracts any remaining uncovered area (voids) from the settlement.

    The input layer's attribute schema is preserved in the output.

    Requires QGIS >= 3.20. Both layers must use a metric CRS (metres).

    Args:
        input_layer: Settlement polygon layer (``QgsVectorLayer`` or file path).
            Must use a metric CRS.
        buildings_layer: Building footprint polygon layer (``QgsVectorLayer``).
        min_empty_area: Area threshold (m²). Building-free voids smaller than
            this are kept. Default: ``MIN_EMPTY_AREA_M2`` (500 m²).
        min_buffer_m: Minimum per-building buffer distance (m).
            Default: ``MIN_BUFFER_M`` (10 m).
        max_buffer_m: Maximum per-building buffer distance (m).
            Default: ``MAX_BUFFER_M`` (100 m).
        workspace_path: Absolute path for debug layer output. Ignored when
            ``debug_mode`` is ``False``.
        debug_mode: When ``True``, saves intermediate layers to
            ``workspace_path`` for visual inspection.

    Returns:
        A ``QgsVectorLayer`` with building-free voids (≥ ``min_empty_area``)
        removed from the settlement polygon. Returns ``input_layer`` unchanged
        when it has no valid features or when no buildings are found.

    Raises:
        Exception: Any unexpected processing error is logged at ``CRITICAL``
            level and re-raised after optionally saving a debug snapshot of
            the input layer.
    """
    Logger.log("ErodeEmptyAreas Start", level="INFO")
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path,
                tool_name=_DEBUG_TOOL_NAME)

    try:
        if isinstance(input_layer, str):
            input_layer = QgsVectorLayer(input_layer, "input", "ogr")

        # Early returns — no Processing invoked
        if not input_layer.isValid() or input_layer.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no valid input features, returning unchanged.",
                level="INFO",
            )
            return input_layer

        if not buildings_layer.isValid() or buildings_layer.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no buildings provided, returning input unchanged.",
                level="INFO",
            )
            return input_layer

        # --- Step 0: Fix input geometries ---
        fixed_input = safe_processing_run("native:fixgeometries", {
            'INPUT': input_layer,
            'METHOD': 1,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(fixed_input, _DEBUG_TOOL_NAME,
                             "step0_fixed", workspace_path)

        # --- Step 1: Select buildings within settlement boundary ---
        Logger.log(
            "ErodeEmptyAreas: Step 1 – selecting buildings within settlement…",
            level="INFO",
        )
        sel_buildings = safe_processing_run("native:extractbylocation", {
            'INPUT': buildings_layer,
            'PREDICATE': [0],   # intersects
            'INTERSECT': fixed_input,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(sel_buildings, _DEBUG_TOOL_NAME,
                             "step1_sel_buildings", workspace_path)
        Logger.log(
            f"ErodeEmptyAreas: {sel_buildings.featureCount()} building(s) selected.",
            level="INFO",
        )

        if sel_buildings.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no buildings within settlement, returning unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 2: Build per-building buffer layer ---
        Logger.log(
            f"ErodeEmptyAreas: Step 2 – computing building buffers "
            f"(min={min_buffer_m} m, max={max_buffer_m} m)…",
            level="INFO",
        )
        buf_layer = _build_buffer_layer(sel_buildings, min_buffer_m, max_buffer_m)
        if debug_mode and workspace_path:
            save_debug_layer(buf_layer, _DEBUG_TOOL_NAME,
                             "step2_building_buffers", workspace_path)

        # --- Step 3: Dissolve buffer union ---
        # Uses collect + buffer(0, dissolve=True) workaround — native:dissolve
        # silently fails on large MultiPolygon datasets (QGIS ≤ 3.40).
        Logger.log(
            "ErodeEmptyAreas: Step 3 – dissolving buffer union…", level="INFO"
        )
        collected = safe_processing_run("native:collect", {
            'INPUT': buf_layer,
            'FIELD': [],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        buffer_union = safe_processing_run("native:buffer", {
            'INPUT': collected,
            'DISTANCE': 0,
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': True,
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(buffer_union, _DEBUG_TOOL_NAME,
                             "step3_buffer_union", workspace_path)

        # --- Step 4: Compute building-free voids ---
        Logger.log(
            "ErodeEmptyAreas: Step 4 – computing empty areas…", level="INFO"
        )
        empty_areas = safe_processing_run("native:difference", {
            'INPUT': fixed_input,
            'OVERLAY': buffer_union,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': TOPOLOGY_GRID_SIZE,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(empty_areas, _DEBUG_TOOL_NAME,
                             "step4_empty_areas", workspace_path)

        empty_single = safe_processing_run("native:multiparttosingleparts", {
            'INPUT': empty_areas,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']

        filtered_empty = safe_processing_run("qgis:extractbyexpression", {
            'INPUT': empty_single,
            'EXPRESSION': f'area($geometry) >= {min_empty_area}',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(filtered_empty, _DEBUG_TOOL_NAME,
                             "step4_filtered_empty_areas", workspace_path)
        Logger.log(
            f"ErodeEmptyAreas: {filtered_empty.featureCount()} void(s) "
            f"(≥ {min_empty_area} m²) to remove.",
            level="INFO",
        )

        if filtered_empty.featureCount() == 0:
            Logger.log(
                "ErodeEmptyAreas: no voids to remove, returning input unchanged.",
                level="INFO",
            )
            return fixed_input

        # --- Step 5: Subtract voids from settlement ---
        Logger.log(
            "ErodeEmptyAreas: Step 5 – subtracting empty areas…", level="INFO"
        )
        result = safe_processing_run("native:difference", {
            'INPUT': fixed_input,
            'OVERLAY': filtered_empty,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
            'GRID_SIZE': TOPOLOGY_GRID_SIZE,
        }, **_dbg)['OUTPUT']
        if debug_mode and workspace_path:
            save_debug_layer(result, _DEBUG_TOOL_NAME,
                             "step5_result", workspace_path)

        Logger.log(
            f"ErodeEmptyAreas End – Output features: {result.featureCount()}",
            level="INFO",
        )
        return result

    except Exception as e:
        if debug_mode and workspace_path and isinstance(input_layer, QgsVectorLayer):
            save_debug_layer(input_layer, _DEBUG_TOOL_NAME, "exception_input",
                             workspace_path, is_error=True)
        Logger.log(f"Error in ErodeEmptyAreas: {str(e)}", level="CRITICAL")
        raise
```

- [ ] **Step 2.2: Run unit tests — confirm they pass**

```
pytest test/test_erode_empty_areas.py -v -m unit
```

Expected output:
```
test/test_erode_empty_areas.py::TestErodeEmptyAreasEarlyReturn::test_empty_input_returns_input_unchanged PASSED
test/test_erode_empty_areas.py::TestErodeEmptyAreasEarlyReturn::test_invalid_input_layer_returns_early PASSED
test/test_erode_empty_areas.py::TestErodeEmptyAreasEarlyReturn::test_empty_buildings_returns_settlement_unchanged PASSED

3 passed
```

- [ ] **Step 2.3: Run full unit test suite — confirm no regressions**

```
pytest test/ -v -m unit
```

Expected: all previously passing unit tests still pass.

- [ ] **Step 2.4: Commit**

```bash
git add ibtool_tools/ErodeEmptyAreas.py test/test_erode_empty_areas.py
git commit -m "feat: implement ErodeEmptyAreas — remove building-free voids from settlements

Buffer distance per building: clamp(sqrt(area), 10, 100) m.
Unit tests cover all three early-return branches (no Processing).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3 — Integrate into `ibtool.py`

**Files:**
- Modify: `ibtool/ibtool.py` (two locations: import line ~73, return statement ~1220)

- [ ] **Step 3.1: Add import**

In `ibtool/ibtool.py`, after line 73 (`from ibtool.ibtool_tools.GapFix import gap_fix`), add:

```python
from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas
```

- [ ] **Step 3.2: Call `erode_empty_areas` after `patch_remove`**

In `_run_partition_pipeline`, find the final two lines of the function:

```python
        return patch_removed, anz_hu
```

Replace with:

```python
        self._update_phase(6, 6, "Erode Empty Areas", 90)
        eroded = erode_empty_areas(
            patch_removed, sel_hu_layer,
            workspace_path=workspace_path,
            debug_mode=debug_mode,
        )
        return eroded, anz_hu
```

- [ ] **Step 3.3: Verify syntax — run import check**

```
python -c "import sys; sys.path.insert(0, '.'); from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas; print('OK')"
```

Expected: `OK`

- [ ] **Step 3.4: Run unit tests — confirm no regressions**

```
pytest test/test_ibtool.py test/test_erode_empty_areas.py -v -m unit
```

Expected: all tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add ibtool/ibtool.py
git commit -m "feat: wire ErodeEmptyAreas as final per-partition pipeline step

Calls erode_empty_areas(patch_removed, sel_hu_layer, ...) in
_run_partition_pipeline after patch_remove.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4 — Domain Documentation

**Files:**
- Write: `ai/domain/erode-empty-areas.md`
- Modify: `docs/how-it-works.md`

- [ ] **Step 4.1: Write domain knowledge file**

Create `ai/domain/erode-empty-areas.md`:

```markdown
# ErodeEmptyAreas — Building-Free Void Removal

## Overview

`ibtool_tools/ErodeEmptyAreas.py` removes areas within settlement polygons
where no buildings are located. It runs as the final per-partition processing
step (Step 09), after `PatchRemove`.

The module works entirely in memory: no intermediate files are written unless
`debug_mode=True`.

---

## Algorithm

```
Input: settlement polygon (patch_remove output)
       buildings layer (sel_hu_layer — buildings in current partition)
    │
    ▼
[Step 0] native:fixgeometries          — repair settlement geometry
    │
    ▼
[Step 1] native:extractbylocation(buildings, settlement, PREDICATE=intersects)
         → sel_buildings: only buildings overlapping the settlement
         If 0 buildings → return input unchanged
    │
    ▼
[Step 2] Per-building buffer (pure Python, QgsGeometry.buffer())
         buf_dist = clamp(sqrt(building.area()), MIN_BUFFER_M, MAX_BUFFER_M)
         All buffer geometries → memory layer "building_buffers"
    │
    ▼
[Step 3] Dissolve buffer union
         native:collect → native:buffer(0, dissolve=True)
         → buffer_union: single polygon covering all building protection zones
    │
    ▼
[Step 4] Compute building-free voids
         native:difference(settlement, buffer_union) → empty_areas
         native:multiparttosingleparts → singlepart
         qgis:extractbyexpression(area >= MIN_EMPTY_AREA_M2) → filtered_empty
         If 0 filtered voids → return fixed_input unchanged
    │
    ▼
[Step 5] native:difference(settlement, filtered_empty)
         → result: settlement with building-free voids removed
```

---

## Buffer Scaling Function

```
buf_dist = max(MIN_BUFFER_M, min(MAX_BUFFER_M, sqrt(building_area)))
```

| Building area (m²) | Buffer (m) | Typical building |
|---|---|---|
| ≤ 100 | **10** (min) | Small shed, garage |
| 2 500 | 50 | Large commercial hall |
| ≥ 10 000 | **100** (max) | Stadium, warehouse |

Rationale: the buffer is proportional to the building's geometric "radius"
(`sqrt(area)` = side length of an equivalent square). This ensures that a
small building protects a reasonable zone around it, while a very large
building protects a wider zone.

---

## Key Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `min_empty_area` | `500.0` m² | Minimum void area to remove; smaller voids are kept |
| `min_buffer_m` | `10.0` m | Lower clamp for the buffer distance |
| `max_buffer_m` | `100.0` m | Upper clamp for the buffer distance |
| `debug_mode` | `False` | Save intermediate layers to `workspace_path` |

---

## Known Limitations / Workarounds

### `native:dissolve` is intentionally avoided

`native:dissolve` silently produces null or empty geometries on large
`MultiPolygon` datasets (QGIS ≤ 3.40). The workaround used throughout this
module (and the rest of the codebase):

```python
# Instead of native:dissolve:
collected = native:collect(input)
dissolved = native:buffer(collected, distance=0, dissolve=True)
```

### Metric CRS required

`sqrt(area)` is interpreted in square metres; buffer distances are in metres.
Passing a geographic CRS (degrees) produces meaningless results.

---

## Error Handling

Any unhandled exception inside `erode_empty_areas` is:
1. Logged at `CRITICAL` level via `Logger.log()`
2. If `debug_mode=True`: the raw input layer is saved as `exception_input`
3. Re-raised to the caller

The function returns the input layer unchanged (without raising) for:
- Invalid or empty settlement layer
- Empty buildings layer
- No buildings spatially within settlement (post-extractbylocation)
- No voids larger than `min_empty_area` found

---

## Debug Layers (when `debug_mode=True`)

All layers written to `{workspace_path}/09_ErodeEmptyAreas/`.

| Suffix | After step | Content |
|---|---|---|
| `step0_fixed` | 0 | Geometry-fixed settlement |
| `step1_sel_buildings` | 1 | Buildings selected within settlement |
| `step2_building_buffers` | 2 | Individual per-building buffer polygons |
| `step3_buffer_union` | 3 | Dissolved union of all building buffers |
| `step4_empty_areas` | 4 | Raw difference (settlement minus buffer union) |
| `step4_filtered_empty_areas` | 4 | Voids passing `min_empty_area` threshold |
| `step5_result` | 5 | Final output |
| `exception_input` | on error | Raw input at time of crash |

---

## Related Files

- `ibtool_tools/ErodeEmptyAreas.py` — implementation
- `ibtool_tools/PatchRemove.py` — previous pipeline step (Step 07)
- `helpers/safe_processing.py` — `safe_processing_run()` wrapper
- `docs/how-it-works.md` — full pipeline overview
```

- [ ] **Step 4.2: Update `docs/how-it-works.md` pipeline diagram**

In `docs/how-it-works.md`, find the pipeline ASCII block (around line 28–53):

```
├── 9. PatchRemove     →  remove splinter areas (< 1 ha, < 20 buildings)
         │
         ▼
Merge all partition results
```

Replace with:

```
├── 9. PatchRemove     →  remove splinter areas (< 1 ha, < 20 buildings)
└── 10. ErodeEmptyAreas → remove building-free voids (≥ 500 m²) from settlement
         │
         ▼
Merge all partition results
```

Also add a new step description section at the end of the "Per-Partition Loop" section (after the `### Step 9 — PatchRemove` section):

```markdown
---

### Step 10 — ErodeEmptyAreas: Remove Building-Free Voids

`ErodeEmptyAreas.py` removes internal areas of the settlement polygon where
no buildings are present. Each building is buffered by
`clamp(sqrt(building_area), 10, 100)` m — small buildings get a 10 m
protection zone, large buildings up to 100 m. Areas inside the settlement
that are not covered by any building buffer and are larger than 500 m² are
subtracted from the settlement polygon.

Sub-steps:

```
INPUT: settlement polygon (from PatchRemove), building footprints

1. Select buildings within settlement boundary
2. Buffer each building by clamp(sqrt(area), 10, 100) m
3. Dissolve all buffers into one union polygon
4. settlement − buffer_union  →  building-free voids
5. Remove voids smaller than 500 m²
6. settlement − filtered_voids  →  cleaned settlement
OUTPUT: settlement polygon with building-free voids removed
```
```

- [ ] **Step 4.3: Commit documentation**

```bash
git add ai/domain/erode-empty-areas.md docs/how-it-works.md
git commit -m "docs: add ErodeEmptyAreas domain doc and update pipeline overview

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Module `ErodeEmptyAreas.py` with constants, `_build_buffer_layer`, `erode_empty_areas` → Task 2
- [x] Buffer formula `clamp(sqrt(area), MIN_BUFFER_M, MAX_BUFFER_M)` → Task 2, Step 2.1
- [x] Unit tests for all 3 early-return branches → Task 1
- [x] Integration in `_run_partition_pipeline` after `patch_remove` → Task 3
- [x] `debug_mode` saves all 8 intermediate layers → Task 2, Step 2.1
- [x] Domain doc `ai/domain/erode-empty-areas.md` → Task 4
- [x] `docs/how-it-works.md` updated → Task 4
- [x] Exception handling with CRITICAL log + re-raise → Task 2, Step 2.1

**No placeholders:** All code blocks are complete.

**Type consistency:**
- `erode_empty_areas` signature matches import in Task 3.
- `_build_buffer_layer` returns `QgsVectorLayer` used in Step 3 of the function.
- `sel_hu_layer` is defined at the start of `_run_partition_pipeline` and in scope at the call site.
