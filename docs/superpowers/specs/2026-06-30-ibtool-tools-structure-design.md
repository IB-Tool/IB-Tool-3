# ibtool_tools — Unified Module Structure

**Date:** 2026-06-30
**Status:** Approved

## Goal

Align all modules under `ibtool_tools/` with the established structure of `GapClose.py` so every file has a consistent layout and is self-documenting at a glance.

## Target Structure (per module)

```
1. encoding declaration  (# -*- coding: utf-8 -*-)
2. Module docstring       short description + Public API listing
3. Imports
4. _DEBUG_TOOL_NAME       section-headed constant
5. Module-level constants section-headed, each with a one-line docstring
6. Private helpers        section-headed, _underscore_prefix functions
7. Public API             section-headed, the exported functions/class
```

Section headers use the separator style from GapClose.py:
```python
# ---------------------------------------------------------------------------
# Section name
# ---------------------------------------------------------------------------
```

## Per-file Change Plan

### AddSingleBuilding.py
- Expand single-line docstring → multi-line with `Public API` block listing `add_single_bdg`
- `_DEBUG_TOOL_NAME` and constants already in correct blocks — no change
- Add `# Public API` header before `add_single_bdg`

### Blocker.py
- Expand single-line docstring → multi-line with `Public API` block listing `blocker`
- `_DEBUG_TOOL_NAME` and constants already correct
- Add `# Private helpers` header before `_build_block_polygons`
- Add `# Public API` header before `blocker`

### EdgeCatch.py
- Add `Public API` section to existing multi-line docstring listing `edge_catch`
- Define `_DEBUG_TOOL_NAME = "05_EdgeCatch"` in debug block
- Remove `DEBUG_TOOL_NAME` from the `edge_catch_utils` import; update the one `save_debug_layer` call to use `_DEBUG_TOOL_NAME`
- No module constants or private helpers → sections skipped
- Add `# Public API` header before `edge_catch`

### FootprintDensity.py
- New module docstring listing `calc_footprint_density`, `footprint_density`, `identify_dense_blocks`
- Define `_DEBUG_TOOL_NAME = "FootprintDensity"` (no pipeline-number prefix; utility module)
- Extract nested `select_block` → top-level `_select_block(input_str_network, input_bdg, buffer, min_bdg_count)` with `min_bdg_count` passed explicitly
- No module constants → section skipped
- Add `# Private helpers` header before `_select_block`
- Add `# Public API` header before `calc_footprint_density`

### HoleClose.py
- New module docstring listing `hole_close`
- Define `_DEBUG_TOOL_NAME = "HoleClose"` (utility module, no pipeline prefix)
- Add `# Module-level constants` header + one-line docstring to existing `_OPERATOR_LESS_THAN_OR_EQUAL`
- No private helpers → section skipped
- Add `# Public API` header before `hole_close`

### ImportFilter.py
- Add `Public API` block to existing docstring, listing `import_filter`, `input_hu_filter`
- `_DEBUG_TOOL_NAME` and constants already correct
- Add `# Private helpers` header before `_create_filter_string`
- Add `# Public API` header before `import_filter`

### ErodeEmptyAreas.py
- Replace current docstring (which lists constants inline) with the GapClose.py style:
  short prose description + `Public API` block listing `erode_empty_areas`
- Constant descriptions stay in the constants section (already there) — removed from docstring
- `_DEBUG_TOOL_NAME`, constants, private helpers, and public API headers already present — no structural change needed beyond the docstring

### PatchRemove.py
- New module docstring listing `patch_remove`
- `_DEBUG_TOOL_NAME` already correct
- Extract the four function-signature defaults to named module constants:
  - `DEFAULT_MIN_PATCH_SIZE = 10_000`
  - `DEFAULT_MIN_BDG_COUNT = 20`
  - `DEFAULT_FOOTPRINT_AREA_SUM = 6_000`
  - `DEFAULT_FOOTPRINT_DENSITY_THRESHOLD = 18`
  Each gets a one-line docstring
- Update `patch_remove` signature to reference these constants as defaults
- No private helpers → section skipped
- Add `# Public API` header before `patch_remove`

### MST_Clustering.py
- New module docstring listing `calc_bounding_rect`, `mst_clustering`
- `_DEBUG_TOOL_NAME` and constants already correct
- Add `# Private helpers` header before `_main_angle`
- Add `# Public API` header before `calc_bounding_rect`

### CreateMST.py
- New module docstring describing the orchestrator pattern; lists `CreateMST` (class) and `calculate_mst` (function)
- Define `_DEBUG_TOOL_NAME = "CreateMST"` (no debug output yet; noted for future)
- No module constants → section skipped
- No private helpers → section skipped
- Add `# Public API` header before `class CreateMST`

## Memory note

`_DEBUG_TOOL_NAME` was added to `HoleClose.py`, `FootprintDensity.py`, and `CreateMST.py` for structural consistency. Debug output (`save_debug_layer` calls) still needs to be implemented in those three files in a future task.

## Out of Scope

- Logic or algorithm changes
- Renaming existing public symbols
- Adding debug calls to the three utility modules (separate task)
- Naming convention cleanup in FootprintDensity.py (PascalCase params)
