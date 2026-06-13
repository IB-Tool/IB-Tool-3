# ErodeEmptyAreas — Design Spec

**Date:** 2026-06-07  
**Status:** Approved  
**Branch:** Add_GapFix

---

## Summary

Add a new processing step `ErodeEmptyAreas` to the IBTool pipeline that removes areas within settlement polygons where no buildings are located. The step runs per partition, immediately after `patch_remove` (Step 07), making it the final per-partition processing step (Step 09).

---

## Problem Statement

After `patch_remove`, a settlement polygon may still contain large internal voids where no buildings stand — e.g. parks, open fields, or water bodies enclosed by building clusters. These void areas inflate the settlement footprint and should be eroded away.

---

## Algorithm

```
Input: settlement polygon (output of patch_remove)
       buildings layer (sel_hu_layer — buildings in current partition)

[Step 0] native:fixgeometries on input
         → fixed_input

[Step 1] native:extractbylocation(buildings_layer, fixed_input, PREDICATE=intersects)
         → sel_buildings
         If sel_buildings.featureCount() == 0: return fixed_input

[Step 2] Per-building buffer (pure Python, QgsGeometry.buffer())
         buf_dist = clamp(sqrt(building.area()), min_buffer_m, max_buffer_m)
         All buffers → memory layer "building_buffers"

[Step 3] Dissolve buffer union
         collect → buffer(0, dissolve=True)
         → buffer_union_layer

[Step 4] Compute empty areas
         native:difference(fixed_input, buffer_union_layer) → empty_areas
         native:multiparttosingleparts → singlepart
         qgis:extractbyexpression(area($geometry) > min_empty_area)
         → filtered_empty_areas
         If filtered_empty_areas.featureCount() == 0: return fixed_input

[Step 5] Subtract empty areas
         native:difference(fixed_input, filtered_empty_areas)
         → result
```

---

## Buffer Scaling Function

```python
buf_dist = max(min_buffer_m, min(max_buffer_m, math.sqrt(building_area)))
```

| Building area (m²) | sqrt(area) | Buffer (m) |
|---|---|---|
| 25 | 5 | **10** (min clamp) |
| 100 | 10 | 10 |
| 2 500 | 50 | 50 |
| 10 000 | 100 | **100** (max clamp) |

Rationale: the buffer is proportional to the building's geometric "radius". Small buildings get the minimum protection zone (10 m), very large buildings get up to 100 m.

---

## Module: `ibtool_tools/ErodeEmptyAreas.py`

### Constants

| Constant | Value | Meaning |
|---|---|---|
| `_DEBUG_TOOL_NAME` | `"09_ErodeEmptyAreas"` | Debug folder prefix; reflects pipeline order |
| `MIN_BUFFER_M` | `10.0` | Minimum per-building buffer distance (m) |
| `MAX_BUFFER_M` | `100.0` | Maximum per-building buffer distance (m) |
| `MIN_EMPTY_AREA_M2` | `500.0` | Minimum area (m²) of an empty region to remove |
| `TOPOLOGY_GRID_SIZE` | `0.00001` | Grid size for difference operations |

### Public Function

```python
def erode_empty_areas(
    input_layer: QgsVectorLayer,
    buildings_layer: QgsVectorLayer,
    min_empty_area: float = MIN_EMPTY_AREA_M2,
    min_buffer_m: float = MIN_BUFFER_M,
    max_buffer_m: float = MAX_BUFFER_M,
    workspace_path: str = None,
    debug_mode: bool = False,
) -> QgsVectorLayer:
```

**Returns:** Cleaned settlement polygon with building-free voids (≥ `min_empty_area`) removed.

**Early returns (no Processing):**
- Input layer invalid or featureCount == 0 → return input_layer unchanged
- No buildings selected in step 1 → return fixed_input unchanged
- No filtered empty areas in step 4 → return fixed_input unchanged

---

## Pipeline Integration (`ibtool/ibtool.py`)

In `_run_partition_pipeline`, add after the `patch_remove` call:

```python
eroded = erode_empty_areas(
    patch_removed, sel_hu_layer,
    workspace_path=workspace_path,
    debug_mode=debug_mode,
)
return eroded, anz_hu
```

Add to imports:
```python
from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas
```

---

## Debug Layers

All layers written to `{workspace_path}/09_ErodeEmptyAreas/`.

| Suffix | After step | Content |
|---|---|---|
| `step0_fixed` | 0 | Geometry-fixed input |
| `step1_sel_buildings` | 1 | Selected buildings within settlement |
| `step2_building_buffers` | 2 | Individual building buffer polygons |
| `step3_buffer_union` | 3 | Dissolved buffer union |
| `step4_empty_areas` | 4 | Raw empty areas (before area filter) |
| `step4_filtered_empty_areas` | 4 | Empty areas passing min_empty_area threshold |
| `step5_result` | 5 | Final result |
| `exception_input` | on error | Raw input at time of crash |

---

## Tests (`test/test_erode_empty_areas.py`)

**Scope: unit tests only** (no QGIS Processing invocation — early return branches).

| Test | What it checks |
|---|---|
| `test_invalid_layer_returns_input` | Invalid `QgsVectorLayer()` → returns early without crash |
| `test_empty_layer_returns_input_unchanged` | Valid but 0-feature layer → returns input unchanged |
| `test_no_buildings_returns_input_unchanged` | Empty buildings layer → returns input unchanged |

---

## Documentation

- **Module docstring** in `ErodeEmptyAreas.py`: algorithm steps, buffer formula, constants table, metric CRS requirement
- **Function docstring**: full Args / Returns / Raises in GapFix style
- **`ai/domain/erode-empty-areas.md`**: algorithm, parameters, debug layers, known limitations
- **`docs/how-it-works.md`**: new pipeline step entry (Step 09)

---

## Constraints and Notes

- **Metric CRS required**: `sqrt(area)` is interpreted in metres.
- **`native:dissolve` avoided**: uses `collect + buffer(0, dissolve=True)` workaround (same as rest of codebase).
- **Attribute preservation**: input attributes (from `patch_remove`) are preserved in the output — the difference operation retains the INPUT layer's schema.
- **Step number**: `09_ErodeEmptyAreas` leaves slot 08 available for `GapFix` integration in a future step.
