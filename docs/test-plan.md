# Test Completion Plan

This document tracks all known test gaps and the order in which they should be addressed.
It is the working backlog for test work — update status fields as steps are completed.

**Reference:** `docs/test-strategy.md` (authoritative strategy), `ai/core/testing-rules.md` (tactical rules)

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| `[ ]`  | Pending |
| `[~]`  | In progress |
| `[x]`  | Done |

---

## Priority 1 — Small effort, high impact

### STEP 1 — `test_qgis_defaults.py` (CREATE NEW)

**Target:** `helpers/qgis_defaults.py`
**Tier:** `@pytest.mark.unit`
**Current state:** 0 tests. Module exists, zero coverage.

**Tests to add:**
- `test_module_imports_without_error` — import succeeds in isolation
- `test_default_constants_have_expected_types` — all constants are int/float/str as documented
- `test_default_values_match_spec` — spot-check 3–5 critical default values against project spec

**Status:** `[x]`

---

### STEP 2 — `test_logger.py` (EXTEND)

**Target:** `helpers/logger.py`
**Tier:** `@pytest.mark.unit`
**Current state:** 4 tests covering log file creation, INFO message routing, invalid level, QGIS level mapping.

**Tests to add:**
- `test_warning_routed_to_qgis_warning_level` — `log(..., level='WARNING')` calls `QgsMessageLog` with `Qgis.Warning`
- `test_critical_routed_to_qgis_critical_level` — same for `CRITICAL`
- `test_log_file_contains_expected_line_format` — written line matches `LEVEL: message` pattern
- `test_close_logger_called_twice_does_not_raise` — `close_logger()` is idempotent
- `test_log_without_message_box_calls_msg` — when no message box is set, `msg()` is called instead

**Status:** `[x]`

---

### STEP 3 — `test_message.py` (EXTEND)

**Target:** `helpers/message.py`
**Tier:** `@pytest.mark.unit`
**Current state:** 2 tests covering string logging and non-string conversion.

**Tests to add:**
- `test_msg_without_registered_message_box_does_not_raise` — calling `msg()` when no box is registered must not raise
- `test_msg_empty_string` — `msg('')` must not raise and logs an empty string
- `test_msg_none_value` — `msg(None)` coerces to string `'None'`

**Status:** `[x]`

---

## Priority 2 — Medium effort

### STEP 4 — `conftest.py` factory consolidation (REFACTOR TEST HELPERS)

**Target:** `test/conftest.py`
**Current state:** conftest.py only sets sys.path. Seven factory patterns are duplicated across 6+ test files.

**Patterns to consolidate (from `docs/test-strategy.md §5.3`):**
1. `make_polygon_layer()` — in-memory polygon layer with optional features
2. `make_line_layer()` — in-memory line layer
3. `make_point_layer()` — in-memory point layer
4. `add_fields_to_layer()` — adds a fixed set of QgsFields
5. `build_square()` — creates a square QgsGeometry from `(x0, y0, size)`
6. `make_feature()` — creates a QgsFeature with given geometry and optional attributes
7. `setup_qgis_app()` — QGIS init (already centralized; remove reimplementations in old files)

**Approach:**
1. Add fixtures/helpers to `conftest.py` using `function` scope for layer factories
2. Update imports in affected test files to remove local definitions
3. Verify all tests still pass after refactor

**Affected test files (to update):**
- `test_edge_catch.py` — has `_polygon_layer`, `_line_layer`, `_square`, `_add`
- `test_patch_remove.py` — has `_polygon_layer`, `_square`, `_add`
- `test_gap_fix.py` — check for duplicates
- `test_blocker.py` — check for duplicates
- `test_footprint_density.py` — check for duplicates
- `test_gap_close.py` — check for duplicates

**Status:** `[ ]`

---

### STEP 5 — `test_edge_catch.py` (EXTEND)

**Target:** `ibtool_tools/EdgeCatch.py`
**Current state:** 6 tests (2 unit, 4 integration). Missing: real gap detection scenario, GEOS validity, performance.

**Tests to add:**
- `test_road_crossing_between_buildings_reduces_feature_count` — road that cuts between groups must reduce or split output; asserts `featureCount < input_count` or geometry difference
- `test_output_geometries_are_geos_valid` — every output geometry passes `geom.isGeosValid()`
- `test_mismatched_crs_is_handled_or_raises` — `@pytest.mark.edge_case` — mismatched CRS between inputs
- `test_performance_with_large_street_network` — `@pytest.mark.performance @pytest.mark.slow` — 100+ road segments, must complete in <30 s

**Status:** `[x]`

---

### STEP 6 — `test_patch_remove.py` (EXTEND)

**Target:** `ibtool_tools/PatchRemove.py`
**Current state:** 6 tests. Missing: GEOS validity check, debug_mode test.

**Tests to add:**
- `test_output_geometries_are_geos_valid` — every output geometry passes `geom.isGeosValid()`
- `test_debug_mode_does_not_change_feature_count` — result with `debug_mode=True` equals result without
- `test_empty_polygon_input_returns_empty_or_valid_layer` — `@pytest.mark.edge_case` — 0 polygons in → valid (possibly empty) layer out

**Status:** `[x]`

---

### STEP 7 — Performance tests for `FootprintDensity`, `GapFix`, `Blocker`

**Target:** `test_footprint_density.py`, `test_gap_fix.py`, `test_blocker.py`
**Tiers:** `@pytest.mark.integration @pytest.mark.performance @pytest.mark.slow`

#### 7a — `test_footprint_density.py`
- `test_performance_with_100_buildings` — 100 buildings + matching grid, must complete in <30 s

#### 7b — `test_gap_fix.py`
- `test_performance_with_100_block_partition` — two partitions of 50 buildings each, must complete in <30 s

#### 7c — `test_blocker.py`
- `test_performance_with_200_buildings` — 200 buildings, must complete in <60 s, no memory crash

**Status:** `[x]`

---

## Priority 3 — Large effort, lower urgency

### STEP 8 — MST test files (CREATE NEW)

**Reference:** `ai/domain/mst-testing.md`

These three test files are planned in the MST strategy but do not yet exist:

#### 8a — `test_mst_components.py` (CREATE NEW)
**Tier:** `@pytest.mark.unit`
**Target functions:** `unique()`, `create_layer_from_edges()`, `polygon_stuetzpunkte_dict()`
**Planned: ~12 tests**

Tests to cover:
- `unique()` with duplicates, empty list, single element
- `create_layer_from_edges()` returns valid layer with correct feature count
- `create_layer_from_edges()` with empty edge list → empty layer
- `polygon_stuetzpunkte_dict()` maps polygon ID to list of support points
- `polygon_stuetzpunkte_dict()` with empty polygon layer → empty dict

**Status:** `[x]`

#### 8b — `test_mst_modules.py` (CREATE NEW)
**Tier:** `@pytest.mark.unit`
**Target classes:** `DelaunayProcessor`, `StreetProcessor`, `MSTCalculator` (if refactored; skip if not yet extracted)
**Planned: ~17 tests**

Tests to cover:
- Delaunay triangulation produces at least n-1 edges for n points
- Street processor filters roads outside bounding box
- MST calculator produces exactly n-1 edges for n connected nodes
- Data class field validation (type assertions)

**Note:** Classes are extracted and fully implemented — test file created.

**Status:** `[x]`

#### 8c — `test_mst_performance_edge_cases.py` (CREATE NEW)
**Tiers:** `@pytest.mark.performance @pytest.mark.slow` + `@pytest.mark.edge_case`
**Planned: ~13 tests**

Tests to cover:
- Small dataset (4 buildings): < 1 s, < 10 MB
- Medium dataset (25 buildings): < 5 s, < 25 MB
- Large dataset (100 buildings): < 30 s, < 100 MB
- Empty building layer → returns None or raises with meaningful message
- Building layer with null geometry → does not crash
- Single building → graceful return (0 or 1 edges)
- All buildings collinear → valid tree produced

**Status:** `[x]`

---

### STEP 9 — `test_create_mst.py` (EXTEND)

**Target:** `ibtool_tools/CreateMST.py`
**Current state:** 6 tests. Target from `ai/domain/mst-testing.md`: ~12 tests overall.

**Tests to add:**
- `test_mst_produces_n_minus_1_edges` — result edge count equals building count minus 1
- `test_all_edge_weights_are_positive` — no zero-length or negative-weight edges
- `test_output_layer_crs_matches_input` — output CRS matches input building layer CRS
- `test_with_complex_building_layout` — irregular shapes, various sizes
- `test_debug_mode_does_not_change_edge_count` — debug mode invariant
- `test_road_length_parameter_affects_result` — varying `road_length` produces different edge sets

**Status:** `[x]`

---

### STEP 10 — `test_ibtool.py` full `run()` orchestration (EXTEND)

**Target:** `ibtool/ibtool.py`
**Current state:** 23 tests. Missing: full `run()` orchestration.

**Tests to add:**
- `test_run_with_mock_iface_does_not_raise` — calls `plugin.run()` with a fully mocked `iface`; asserts no exception
- `test_run_shows_dialog_on_first_call` — dialog is shown (or `exec_()` called) when `run()` is invoked
- `test_run_on_second_call_uses_existing_dialog` — second `run()` call reuses, not recreates, the dialog

**Note:** Requires careful mocking of the Qt widget layer. Only implement if mocking can be done without running the Qt event loop.

**Status:** `[x]`

---

## Summary Table

| Step | File | Action | Priority | Status |
|------|------|--------|----------|--------|
| 1 | `test_qgis_defaults.py` | CREATE | P1 | `[x]` |
| 2 | `test_logger.py` | EXTEND (+5 tests) | P1 | `[x]` |
| 3 | `test_message.py` | EXTEND (+3 tests) | P1 | `[x]` |
| 4 | `conftest.py` + `layer_factories.py` | CONSOLIDATE factories | P2 | `[x]` |
| 5 | `test_edge_catch.py` | EXTEND (+5 tests) | P2 | `[x]` |
| 6 | `test_patch_remove.py` | EXTEND (+3 tests) | P2 | `[x]` |
| 7a | `test_footprint_density.py` | EXTEND (+1 perf test) | P2 | `[x]` |
| 7b | `test_gap_fix.py` | EXTEND (+1 perf test) | P2 | `[x]` |
| 7c | `test_blocker.py` | EXTEND (+1 perf test) | P2 | `[x]` |
| 8a | `test_mst_components.py` | CREATE (~12 tests) | P3 | `[x]` |
| 8b | `test_mst_modules.py` | CREATE (~17 tests) | P3 | `[x]` |
| 8c | `test_mst_performance_edge_cases.py` | CREATE (~13 tests) | P3 | `[x]` |
| 9 | `test_create_mst.py` | EXTEND (+6 tests) | P3 | `[x]` |
| 10 | `test_ibtool.py` | EXTEND (+3 tests) | P3 | `[x]` |

---

## Execution Order

Work top-to-bottom in the summary table. Each step is independent unless noted.

- Steps 1–3: No QGIS Processing required — run with `pytest test/ -m "unit"`.
- Step 4: Pure refactoring — run full suite after each file update to verify no regression.
- Steps 5–9c: Require Docker or local QGIS — run with `docker run --rm qgis-plugin-test`.
- Step 10: Requires Qt mocking assessment — evaluate before implementing.

---

## Exclusions (no action needed)

| Item | Reason |
|------|--------|
| `classFactory()` in `__init__.py` | Requires live QGIS `iface` — covered by smoke test in CI |
| Signal/slot wiring in `ibtool_dialog.py` | Qt event loop not available in test env — tested manually |
| Processing-delegating wrappers in `geometry_utils.py` | Indirectly covered by tool integration tests |
| `test_fixtures_mst.py` `MSTTestFixtures` | Fixture helper, not production code — no test by design |