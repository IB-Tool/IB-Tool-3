schritt # Test Strategy

## 1. Purpose and Scope

This document is the single authoritative reference for **why** the test suite is structured the way it is, **how** to choose the right test tier for a new test, and **where** known coverage gaps exist.

**What this document is not:**
- A tutorial on pytest syntax — see the pytest documentation.
- A list of tactical rules for geometry checks or test structure — see [`ai/core/testing-rules.md`](../ai/core/testing-rules.md).
- An MST-specific test catalog — see [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md).

**Who should read this:** Any developer about to write a new test, assess coverage, or understand CI failures.

---

## 2. Test Philosophy

Five principles explain the structural decisions made in this project:

### 2.1 Geometry bugs produce plausible-looking wrong results

A dissolve that silently fails returns an empty or null geometry — not an exception. A polygon that self-intersects still renders on screen. This is why **geometry validity checks are mandatory** for every test that touches a layer-returning function. Checking only `featureCount > 0` is insufficient.

### 2.2 `processing.run()` is the unit/integration boundary

The demarcation between unit and integration tests is not "uses QGIS API" but specifically **whether `processing.run()` is called**. Functions that use `QgsVectorLayer("…memory")`, `QgsFeature`, or `QgsGeometry` directly can be unit-tested without the full Processing framework. Functions that delegate to QGIS algorithms (e.g. `native:dissolve`, `native:buffer`) require an initialized Processing environment and are integration tests.

### 2.3 Error paths are first-class citizens

Empty layers, null geometries, mismatched CRS, and missing partitions are not accidents — they are guaranteed inputs in a geospatial pipeline. Every tool's error-handling branch must be tested explicitly, not just the happy path.

### 2.4 Tests document expected behavior

Constants, thresholds, and accepted defaults should be visible in test docstrings or assertions, not buried in source code. A test like `assert density > 0.5` without explanation is opaque. A test with `"""Density floor is 0.5 per km² per project spec."""` is documentation.

### 2.5 `debug_mode=True` must not alter return values

The debug branch of every processing tool must be exercised in tests. The invariant: enabling debug mode may write additional layers to disk but must not change the function's return value, raise new exceptions, or alter the geometry of output features.

---

## 3. Test Taxonomy

Four tiers are used. Every test must carry exactly one tier marker and may additionally carry `edge_case`.

### 3.1 Unit (`@pytest.mark.unit`)

**Definition:** No call to `processing.run()`. No file I/O. May instantiate `QgsVectorLayer("…memory")`, `QgsFeature`, or `QgsGeometry` directly.

**When to use:** Testing a pure function, a helper utility, configuration parsing, or any logic that does not invoke a QGIS Processing algorithm.

**Execution:** Runs anywhere Python + QGIS libraries are installed. Does not require Docker.

**Example targets:** `check.py`, `config_manager.py`, `system_utils.py`, `mst_utils.py`, `debug_utils.py`, individual math or geometry helper functions.

### 3.2 Integration (`@pytest.mark.integration`)

**Definition:** Calls `processing.run()` at least once, directly or indirectly through the module under test.

**When to use:** Testing a full processing tool (`GapClose`, `Blocker`, `FootprintDensity`, etc.) or any helper that delegates to a QGIS algorithm.

**Execution:** Requires Docker (`docker run --rm qgis-plugin-test`) or a local QGIS installation with Processing initialized.

**Example targets:** All `ibtool_tools/` modules, `geometry_utils.py` functions that call `native:*` algorithms.

### 3.3 Edge case (`@pytest.mark.edge_case`)

**Definition:** Cross-cutting tag combined with `unit` or `integration`. Marks a test that exercises a boundary or degenerate input.

**Catalog of mandatory edge cases for layer-processing tools:**
- Empty input layer (0 features)
- Layer with null geometry on one or more features
- Layer with 0 features after filtering
- Mismatched CRS between inputs
- Multipart geometry where singlepart is expected
- Partition ID `-1` (unassigned features in Blocker output)

### 3.4 Performance (`@pytest.mark.performance` + `@pytest.mark.slow`)

**Definition:** Exercises time or memory bounds on datasets of more than 50 features. Always carries both `performance` and `slow`.

**When to use:** Validating that a tool finishes within an acceptable time budget on a realistic dataset size.

**Execution:** Excluded from fast local runs via `-m "not slow"`. Always runs in CI.

**Example targets:** `Blocker` with 200+ buildings, `FootprintDensity` with large grid, MST with 100 buildings.

---

## 4. Coverage Targets

These are per-category floor values, not aspirational goals. Coverage below these thresholds signals a gap that should be addressed before merging new features.

| Module Category | Files | Target |
|---|---|---|
| Pure Python helpers | `check.py`, `config_manager.py`, `system_utils.py` | 90% |
| QGIS-wrapping helpers | `data_loader.py`, `geometry_utils.py`, `safe_processing.py`, `debug_utils.py`, `mst_utils.py`, `edge_catch_utils.py` | 80% |
| Logger / message infrastructure | `logger.py`, `message.py` | 75% |
| Constants file | `qgis_defaults.py` | Smoke test only (instantiation + default values) |
| All `ibtool_tools/` geometry tools | `GapClose.py`, `HoleClose.py`, `EdgeCatch.py`, `AddSingleBuilding.py`, `PatchRemove.py`, `ImportFilter.py`, `FootprintDensity.py`, `GapFix.py` | 80% |
| Complex multi-step tools | `Blocker.py`, `MST_Clustering.py` | 75% |
| MST tools | `CreateMST.py` | See [`ai/domain/mst-testing.md`](../ai/domain/mst-testing.md) (overall >90%, core algorithms >95%) |
| UI layer | `ibtool/ibtool.py`, `ibtool/ibtool_dialog.py` | 65–70% |
| Plugin entry / smoke | `__init__.py`, `ibtool/ibtool.py` `classFactory` | Smoke only |
| **Overall project** | — | **75%** |

---

## 5. Test Data and Fixture Strategy

### 5.1 Shared vs. per-file fixtures

**Shared (in `test/conftest.py`):** Generic factories that have no domain-specific geometry layout. Any test file may depend on these without importing from another test module.

Current shared fixtures / helpers:
- `empty_polygon_layer()` — returns an empty `QgsVectorLayer` with Polygon geometry
- `empty_line_layer()` — returns an empty `QgsVectorLayer` with LineString geometry
- `square_geometry_factory` — callable that creates a square `QgsGeometry` at a given origin
- `add_feature_to_layer()` — helper to add a `QgsFeature` with given geometry and attributes
- `crs_25833` — `QgsCoordinateReferenceSystem` for EPSG:25833
- `dummy_data_dir` — `pathlib.Path` pointing to `Testdaten/`

**Per-file:** Domain-specific layouts (exact building positions, street networks, block structures) stay in the file that uses them. Example: `_make_two_block_layer()` in `test_gap_fix.py`.

### 5.2 Fixture scope rules

| Fixture type | Scope |
|---|---|
| `QgsVectorLayer` instances | `function` — layers are mutable; reuse across tests causes interference |
| `QgsApplication` (QGIS singleton) | `session` — expensive to initialize, safe to share read-only |
| `QgsCoordinateReferenceSystem` | `session` — immutable value object |
| File paths (`pathlib.Path`) | `session` — path strings are immutable |

### 5.3 Duplicate factory functions (consolidation backlog)

The following factory patterns are currently duplicated across 6+ test files and should eventually be consolidated into `conftest.py`:

1. `make_polygon_layer()` / `create_polygon_layer()` — creates a memory polygon layer with features
2. `make_line_layer()` / `create_line_layer()` — creates a memory line layer
3. `make_point_layer()` — creates a memory point layer
4. `add_fields_to_layer()` — adds a fixed set of QgsFields to a layer
5. `build_square()` / `make_square_geom()` — creates a square QgsGeometry from bbox
6. `make_feature()` / `build_feature()` — creates a QgsFeature with given geometry
7. `setup_qgis_app()` — initializes QgsApplication; already centralized but reimplemented in some older test files

---

## 6. Module-to-Test Mapping

Cross-reference of every production module, its test file, approximate test count, dominant tier, and known gaps.

### helpers/

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `check.py` | `test_check.py` | 65 | unit | None significant |
| `config_manager.py` | `test_config_manager.py` | 52 | unit | None significant |
| `system_utils.py` | `test_manage_directory.py` | 19 | unit | — |
| `data_loader.py` | `test_data_loader.py` | 15 | unit | Integration tests for file-loading paths |
| `geometry_utils.py` | `test_geometry_utils.py` | 24 | unit | Processing-delegating wrappers untested (see §9) |
| `safe_processing.py` | `test_safe_processing.py` | 8 | unit | — |
| `debug_utils.py` | `test_debug_utils.py` | 14 | unit | — |
| `mst_utils.py` | `test_mst_utils.py` | 19 | unit | — |
| `edge_catch_utils.py` | `test_edge_catch_utils.py` | 24 | unit | — |
| `logger.py` | `test_logger.py` | 4 | unit | WARNING/CRITICAL routing, log file format, `close_logger()` idempotency |
| `message.py` | `test_message.py` | 2 | unit | Missing message box path |
| `qgis_defaults.py` | *(none)* | 0 | — | Zero tests; smoke test needed |

### ibtool_tools/

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `Blocker.py` | `test_blocker.py` | 23 | integration | Performance tests for large datasets |
| `CreateMST.py` | `test_create_mst.py` | 6 | integration | See `ai/domain/mst-testing.md` |
| `MST_Clustering.py` | `test_mst_clustering.py` | 10 | integration | — |
| `FootprintDensity.py` | `test_footprint_density.py` | 10 | integration | Performance tests |
| `ImportFilter.py` | `test_import_filter.py` | 14 | integration | — |
| `GapClose.py` | `test_gap_close.py` | 15 | integration | — |
| `HoleClose.py` | `test_hole_close.py` | 25 | integration | — |
| `EdgeCatch.py` | `test_edge_catch.py` | 6 | integration | Known-gap, no-gap, performance cases |
| `AddSingleBuilding.py` | `test_add_single_building.py` | 8 | integration | — |
| `PatchRemove.py` | `test_patch_remove.py` | 6 | integration | Below/above-threshold, empty layer |
| `GapFix.py` | `test_gap_fix.py` | 12 | integration | — |

### ibtool/ (UI + plugin)

| Production module | Test file | ~Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `ibtool/ibtool.py` | `test_ibtool.py` | 23 | unit | Full `run()` orchestration (§9) |
| `ibtool/ibtool_dialog.py` | `test_ibtool_dialog.py` | 35 | unit | Signal/slot wiring (§9) |
| `__init__.py` | `test_init.py` | 1 | smoke | `classFactory()` with live `iface` |

### Infrastructure / environment

| File | Test file | ~Tests | Notes |
|---|---|---|---|
| (MST fixtures) | `test_fixtures_mst.py` | 0 | Helper module, not directly tested |
| (MST test runner) | — | — | `run_mst_tests.py` is a runner, not a test |
| — | `test_qgis_environment.py` | 2 | Smoke: QGIS init and Processing available |
| — | `test_resources.py` | 1 | Smoke: plugin resources compiled |
| — | `test_translations.py` | 1 | Smoke: translation file present |

---

## 7. Decision Guide for New Tests

Use this 6-step checklist when adding a new test.

### Step 1 — Identify what changed

- New function or class → write a test for its normal behavior + at least one edge case.
- Bug fix → write a regression test that reproduces the original bug, then verifies the fix.
- Edge case discovered during code review → add to the existing test class under `@pytest.mark.edge_case`.

### Step 2 — Choose the tier

```
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

## 8. Gap Analysis and Prioritized Backlog

### Priority 1 — Small effort, high impact

| Gap | Action |
|---|---|
| `qgis_defaults.py` has zero tests | Add `test_qgis_defaults.py` with smoke tests asserting default constant values |
| `test_logger.py` has only 4 tests | Add: WARNING/CRITICAL log routing; log file line format; `close_logger()` called twice does not raise |
| `test_message.py` has only 2 tests | Add: behavior when no message box is registered |
| `pytest.ini` missing `unit`, `edge_case`, `performance` markers | Register markers (done — see §2 of deliverables) |

### Priority 2 — Medium effort

| Gap | Action |
|---|---|
| 7 duplicate factory functions across 6+ test files (§5.3) | Consolidate into `conftest.py`; update imports in affected test files |
| `test_edge_catch.py`: 6 tests, thin coverage | Add: known-gap detection, no-gap input, performance with large street network |
| `test_patch_remove.py`: 6 tests, thin coverage | Add: feature below area threshold kept, feature above threshold removed, empty input layer |
| Performance tests missing for `FootprintDensity`, `GapFix`, `Blocker` | Add `@pytest.mark.performance` + `@pytest.mark.slow` tests with 100+ feature datasets |

### Priority 3 — Large effort, lower urgency

| Gap | Action |
|---|---|
| No full `run()` orchestration test for `ibtool/ibtool.py` | Add integration test that calls the full plugin `run()` with mock `iface` |
| Integration tests for Processing-delegating helpers in `geometry_utils.py` | Add integration tests for the wrappers identified in §9 |

---

## 9. Justified Exclusions

These are documented decisions that **are not gaps** — they are known exclusions with stated reasons.

| Module / function | Reason for exclusion |
|---|---|
| `ibtool/__init__.py` `classFactory()` | Requires a live `iface` object provided by the running QGIS application. Tested via smoke tests in `test_init.py` and the Docker CI run. |
| Processing-delegating wrappers in `geometry_utils.py` (e.g. functions that call `native:dissolve`, `native:buffer`) | These are thin wrappers around QGIS algorithms. They are indirectly tested by every integration test for tools that use them (e.g. `test_blocker.py`, `test_hole_close.py`). Adding direct tests would duplicate coverage without adding value. |
| `ibtool_dialog.py` signal/slot wiring | The Qt event loop is not available in the test environment. Wiring is tested manually in QGIS. UI widget presence is covered by `test_ibtool_dialog.py`. |
| `test_fixtures_mst.py` `MSTTestFixtures` class | This is a fixture helper, not production code. It has no test of its own by design. |

---

## 10. CI/CD Summary

Tests run automatically on every push to `master`/`main` and on every pull request via GitHub Actions (`.github/workflows/ci.yml`).

### Pipeline steps

1. **Build Docker image** — `docker build --pull -t qgis-plugin-test .`
2. **Run tests with coverage** — `docker run --rm -v $(pwd):/plugins/ibtool qgis-plugin-test`
   - Runs `pytest test/ -v --tb=short --durations=10` with coverage
   - Writes `coverage.xml` to the mounted volume
3. **Fix coverage paths** — replaces container-absolute paths with relative paths for Codecov
4. **Upload to Codecov** — `codecov/codecov-action@v5` with token from repository secrets

### Useful local commands

```bash
# Fast local run — unit tests only (no QGIS Processing required)
pytest test/ -m "unit" -v

# Skip slow tests
pytest test/ -m "not slow" -v

# Full run (requires Docker or local QGIS)
docker run --rm qgis-plugin-test

# Coverage report
pytest test/ --cov=. --cov-report=html
open htmlcov/index.html

# Single module
pytest test/test_blocker.py -v

# Run all MST tests
pytest test/test_*mst*.py test/test_create_mst.py -v
```

### Marker cheatsheet

```bash
pytest test/ -m "unit"              # unit tests only
pytest test/ -m "integration"       # integration tests only
pytest test/ -m "edge_case"         # edge case tests only
pytest test/ -m "not slow"          # skip performance tests
pytest test/ -m "unit and edge_case" # unit edge cases only
```
