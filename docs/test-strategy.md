# Test Strategy

This document is the single authoritative reference for **why** the test suite is structured the way it is, **how** to choose the right test tier for a new test, and **where** known coverage gaps exist. Consult it before writing any new test or assessing CI failures.

**What this document is not:**
- A tutorial on pytest syntax — see the pytest documentation.
- A list of tactical rules for geometry checks or test structure — see [`ai/core/testing-rules.md`](../ai/core/testing-rules.md).
- An MST-specific test catalog — see [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md).

---

## Test Philosophy

Five principles explain the structural decisions made in this project:

### Geometry bugs produce plausible-looking wrong results

A dissolve that silently fails returns an empty or null geometry — not an exception. A polygon that self-intersects still renders on screen. This is why **geometry validity checks are mandatory** for every test that touches a layer-returning function. Checking only `featureCount > 0` is insufficient.

### `processing.run()` is the unit/integration boundary

The demarcation between unit and integration tests is not "uses QGIS API" but specifically **whether `processing.run()` is called**. Functions that use `QgsVectorLayer("…memory")`, `QgsFeature`, or `QgsGeometry` directly can be unit-tested without the full Processing framework. Functions that delegate to QGIS algorithms (e.g. `native:dissolve`, `native:buffer`) require an initialized Processing environment and are integration tests.

### Error paths are first-class citizens

Empty layers, null geometries, mismatched CRS, and missing partitions are not accidents — they are guaranteed inputs in a geospatial pipeline. Every tool's error-handling branch must be tested explicitly, not just the happy path.

### Tests document expected behavior

Constants, thresholds, and accepted defaults should be visible in test docstrings or assertions, not buried in source code. A test like `assert density > 0.5` without explanation is opaque. A test with `"""Density floor is 0.5 per km² per project spec."""` is documentation.

### `debug_mode=True` must not alter return values

The debug branch of every processing tool must be exercised in tests. The invariant: enabling debug mode may write additional layers to disk but must not change the function's return value, raise new exceptions, or alter the geometry of output features.

---

## Test Taxonomy

Four tiers are used. Every test must carry exactly one tier marker and may additionally carry `edge_case`.

### Unit (`@pytest.mark.unit`)

**Definition:** No call to `processing.run()`. No file I/O. May instantiate `QgsVectorLayer("…memory")`, `QgsFeature`, or `QgsGeometry` directly.

**When to use:** Testing a pure function, a helper utility, configuration parsing, or any logic that does not invoke a QGIS Processing algorithm.

**Execution:** Runs anywhere Python + QGIS libraries are installed. Does not require Docker.

**Example targets:** `check.py`, `config_manager.py`, `system_utils.py`, `mst_utils.py`, `debug_utils.py`, individual math or geometry helper functions.

### Integration (`@pytest.mark.integration`)

**Definition:** Calls `processing.run()` at least once, directly or indirectly through the module under test.

**When to use:** Testing a full processing tool (`GapClose`, `Blocker`, `FootprintDensity`, etc.) or any helper that delegates to a QGIS algorithm.

**Execution:** Requires Docker (`docker run --rm qgis-plugin-test`) or a local QGIS installation with Processing initialized.

**Example targets:** All `ibtool_tools/` modules, `geometry_utils.py` functions that call `native:*` algorithms.

### Edge case (`@pytest.mark.edge_case`)

**Definition:** Cross-cutting tag combined with `unit` or `integration`. Marks a test that exercises a boundary or degenerate input.

**Catalog of mandatory edge cases for layer-processing tools:**
- Empty input layer (0 features)
- Layer with null geometry on one or more features
- Layer with 0 features after filtering
- Mismatched CRS between inputs
- Multipart geometry where singlepart is expected
- Partition ID `-1` (unassigned features in Blocker output)

### Performance (`@pytest.mark.performance` + `@pytest.mark.slow`)

**Definition:** Exercises time or memory bounds on datasets of more than 50 features. Always carries both `performance` and `slow`.

**When to use:** Validating that a tool finishes within an acceptable time budget on a realistic dataset size.

**Execution:** Excluded from fast local runs via `-m "not slow"`. Always runs in CI.

**Example targets:** `Blocker` with 200+ buildings, `FootprintDensity` with large grid, MST with 100 buildings.

---

## Coverage Targets

These are per-category floor values, not aspirational goals. Coverage below these thresholds signals a gap that should be addressed before merging new features.

| Module Category | Files | Target |
|---|---|---|
| Pure Python helpers | `check.py`, `config_manager.py`, `system_utils.py` | 90% |
| QGIS-wrapping helpers | `data_loader.py`, `geometry_utils.py`, `safe_processing.py`, `debug_utils.py`, `mst_utils.py`, `edge_catch_utils.py` | 80% |
| Logger / message infrastructure | `logger.py`, `message.py` | 75% |
| Constants file | `qgis_defaults.py` | Smoke test only (instantiation + default values) |
| All `ibtool_tools/` geometry tools | `GapClose.py`, `HoleClose.py`, `EdgeCatch.py`, `AddSingleBuilding.py`, `PatchRemove.py`, `ImportFilter.py`, `FootprintDensity.py` | 80% |
| Complex multi-step tools | `Blocker.py`, `MST_Clustering.py` | 75% |
| MST tools | `CreateMST.py` | See [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md) (overall >90%, core algorithms >95%) |
| UI layer | `ibtool/ibtool.py`, `ibtool/ibtool_dialog.py` | 65–70% |
| Plugin entry / smoke | `__init__.py`, `ibtool/ibtool.py` `classFactory` | Smoke only |
| **Overall project** | — | **75%** |

---

## Test Data and Fixture Strategy

### Shared vs. per-file factories

**`conftest.py`** handles only pytest infrastructure: it adds the plugin root to `sys.path` and registers the `ibtool` package stub so that absolute imports resolve correctly in both local and Docker environments. It does **not** provide pytest fixtures or import QGIS modules — doing so would trigger a circular import error via `qgis.utils._import` before QGIS is initialized.

**`test/layer_factories.py`** is the canonical home for all shared layer and geometry factory helpers. It is a regular Python module (not a pytest plugin) and must be imported **after** calling `get_qgis_app()` in each test file:

```python
from .utilities import get_qgis_app
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import (
    make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer
)
```

Current functions in `layer_factories.py`:
- `make_polygon_layer(crs, name)` — empty in-memory polygon layer
- `make_line_layer(crs, name)` — empty in-memory line layer
- `make_square_geom(x0, y0, size)` — axis-aligned square `QgsGeometry`
- `add_feature_to_layer(layer, geom)` — adds a `QgsFeature` and returns it

**Per-file:** Domain-specific layouts (exact building positions, street networks, block structures) stay in the file that uses them. Example: `_make_two_block_layer()` in `test_gap_close.py`.

### Fixture scope rules

| Fixture type | Scope |
|---|---|
| `QgsVectorLayer` instances | `function` — layers are mutable; reuse across tests causes interference |
| `QgsApplication` (QGIS singleton) | `session` — expensive to initialize, safe to share read-only |
| `QgsCoordinateReferenceSystem` | `session` — immutable value object |
| File paths (`pathlib.Path`) | `session` — path strings are immutable |

---

## Module-to-Test Mapping

Cross-reference of every production module, its test file, approximate test count, dominant tier, and known gaps.

### helpers/

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `check.py` | `test_check.py` | 73 | unit | None significant |
| `config_manager.py` | `test_config_manager.py` | 56 | unit | None significant |
| `system_utils.py` | `test_manage_directory.py` | 22 | unit | — |
| `data_loader.py` | `test_data_loader.py` | 15 | unit | Integration tests for file-loading paths |
| `geometry_utils.py` | `test_geometry_utils.py` | 41 | unit | Processing-delegating wrappers untested (see Justified Exclusions) |
| `safe_processing.py` | `test_safe_processing.py` | 8 | unit | — |
| `debug_utils.py` | `test_debug_utils.py` | 14 | unit | — |
| `mst_utils.py` | `test_mst_utils.py` | 19 | unit | — |
| `edge_catch_utils.py` | `test_edge_catch_utils.py` | 67 | unit | — |
| `logger.py` | `test_logger.py` | 14 | unit | — |
| `message.py` | `test_message.py` | 5 | unit | — |
| `qgis_defaults.py` | `test_qgis_defaults.py` | 12 | unit | — |

### ibtool_tools/

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `Blocker.py` | `test_blocker.py` | 24 | integration | Performance tests for large datasets |
| `CreateMST.py` | `test_create_mst.py` | 12 | integration | See `ai/domain/mst-testing.md` |
| `MST_Clustering.py` | `test_mst_clustering.py` | 25 | integration | — |
| `FootprintDensity.py` | `test_footprint_density.py` | 11 | integration | Performance tests |
| `ImportFilter.py` | `test_import_filter.py` | 21 | integration | — |
| `GapClose.py` | `test_gap_close.py` | 15 | integration | — |
| `HoleClose.py` | `test_hole_close.py` | 25 | integration | — |
| `EdgeCatch.py` | `test_edge_catch.py` | 14 | integration | Performance cases |
| `AddSingleBuilding.py` | `test_add_single_building.py` | 8 | integration | — |
| `PatchRemove.py` | `test_patch_remove.py` | 9 | integration | — |
| `ErodeEmptyAreas.py` | `test_erode_empty_areas.py` | 17 | unit + integration | Performance tests |

### ibtool/ (UI + plugin)

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `ibtool/ibtool.py` | `test_ibtool.py` | 54 | unit | Full `run()` orchestration |
| `ibtool/ibtool_dialog.py` | `test_ibtool_dialog.py` | 68 | unit | Signal/slot wiring |
| `__init__.py` | `test_init.py` | 1 | smoke | `classFactory()` with live `iface` |

### Infrastructure / environment

| File | Test file | ~Tests | Notes |
|---|---|---|---|
| `scripts/create_release_zip.py` | `test_create_release_zip.py` | 36 | Pure-Python unit tests; no QGIS dependency |
| (MST fixtures) | `test_fixtures_mst.py` | 0 | Helper module, not directly tested |
| — | `test_qgis_environment.py` | 2 | Smoke: QGIS init and Processing available |
| — | `test_resources.py` | 1 | Smoke: plugin resources compiled |
| — | `test_translations.py` | 1 | Smoke: translation file present |

---

## Decision Guide for New Tests

Use this 6-step checklist when adding a new test.

### Step 1 — Identify what changed

- New function or class → write a test for its normal behavior + at least one edge case.
- Bug fix → write a regression test that reproduces the original bug, then verifies the fix.
- Edge case discovered during code review → add to the existing test class under `@pytest.mark.edge_case`.

### Step 2 — Choose the tier

```text
Does the function under test call processing.run()?
├── No  → @pytest.mark.unit
└── Yes → @pytest.mark.integration
            (also requires Docker / local QGIS for execution)

Is this testing a boundary / degenerate input?
└── Yes → additionally add @pytest.mark.edge_case

Will the test use datasets of >50 features or measure time/memory?
└── Yes → additionally add @pytest.mark.performance and @pytest.mark.slow
```

### Step 3 — Choose the test file

Always add to `test_{module_name}.py` where `module_name` is the file under test without extension. If the file does not exist, create it following the class structure in `ai/core/testing-rules.md`.

### Step 4 — Mandatory geometry checks

Every test for a function that returns a `QgsVectorLayer` must include:

```python
assert result_layer is not None
assert result_layer.featureCount() > 0          # or == expected_count
for feat in result_layer.getFeatures():
    geom = feat.geometry()
    assert not geom.isNull(),    "Geometry must not be null"
    assert not geom.isEmpty(),   "Geometry must not be empty"
    assert geom.isGeosValid(),   "Geometry must be GEOS-valid"
```

### Step 5 — Test the debug branch

If the module has a `debug_mode` parameter:

```python
def test_normal_case_with_debug_mode(self, sample_layer):
    """Debug mode produces same result as non-debug mode."""
    result_normal = tool_function(sample_layer, debug_mode=False)
    result_debug  = tool_function(sample_layer, debug_mode=True)
    assert result_debug.featureCount() == result_normal.featureCount()
```

The debug run must not raise an exception and must not change the feature count or geometry of the output.

### Step 6 — Write a one-line docstring

Every test method must have a docstring in the imperative mood describing what behavior it verifies:

```python
def test_gap_is_closed_when_below_threshold(self):
    """Closes gaps smaller than the threshold distance."""
```

---

## Gap Analysis and Prioritized Backlog

### Priority 1 — Small effort, high impact

| Gap | Action |
|---|---|
| Performance tests missing for `FootprintDensity` | Add `@pytest.mark.performance` + `@pytest.mark.slow` tests with 100+ feature datasets |
| Performance tests missing for `Blocker` | Add `@pytest.mark.performance` + `@pytest.mark.slow` test with 200+ buildings |
| `EdgeCatch` performance coverage thin | Add performance test with a large street network dataset |

### Priority 2 — Large effort, lower urgency

| Gap | Action |
|---|---|
| No full `run()` orchestration test for `ibtool/ibtool.py` | Add integration test that calls the full plugin `run()` with mock `iface` |
| Integration tests for Processing-delegating helpers in `geometry_utils.py` | Add integration tests for the wrappers identified in Justified Exclusions |

---

## Justified Exclusions

These are documented decisions that **are not gaps** — they are known exclusions with stated reasons.

| Module / function | Reason for exclusion |
|---|---|
| `ibtool/__init__.py` `classFactory()` | Requires a live `iface` object provided by the running QGIS application. Tested via smoke tests in `test_init.py` and the Docker CI run. |
| Processing-delegating wrappers in `geometry_utils.py` | These are thin wrappers around QGIS algorithms. They are indirectly tested by every integration test for tools that use them (e.g. `test_blocker.py`, `test_hole_close.py`). Adding direct tests would duplicate coverage without adding value. |
| `ibtool_dialog.py` signal/slot wiring | The Qt event loop is not available in the test environment. Wiring is tested manually in QGIS. UI widget presence is covered by `test_ibtool_dialog.py`. |
| `test_fixtures_mst.py` `MSTTestFixtures` class | This is a fixture helper, not production code. It has no test of its own by design. |

---

## CI/CD

For the full CI/CD pipeline description, Docker environment setup, and local commands, see [docs/contributing.md](contributing.md).

Quick reference for common test runs:

```bash
# Unit tests only (no QGIS Processing required)
pytest test/ -m "unit" -v

# Skip slow tests
pytest test/ -m "not slow" -v

# Full run (requires Docker or local QGIS)
docker run --rm qgis-plugin-test

# Coverage report
pytest test/ --cov=. --cov-report=html

# Single module
pytest test/test_blocker.py -v
```

---

## Related Files

| File | Content |
|------|---------|
| [`docs/contributing.md`](contributing.md) | CI/CD pipeline, Docker environment, full test file list, code linting |
| [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) | Tactical rules: geometry checks, test structure, framework conventions |
| [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md) | MST-specific test catalog, fixtures, performance benchmarks |
