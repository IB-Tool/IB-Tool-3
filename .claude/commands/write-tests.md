---
description: Use this skill when the user asks to write, create, or add tests for a module, function, or class — for example "schreib Tests für GapClose", "write tests for the blocker", "add test coverage for X", "fehlende Tests ergänzen". Invoke automatically whenever a testing task is identified for this QGIS plugin project.
---

# /write-tests — Write Tests for an IB-Tool 3 Module

Write pytest tests for the module: **$ARGUMENTS**

Follow these steps in order. Do not skip any step.

---

## Step 1 — Read the target module

Search for `$ARGUMENTS` in these locations (in order):
- `ibtool_tools/$ARGUMENTS.py`
- `helpers/$ARGUMENTS.py`
- Try case variations (e.g. `GapClose` → `gap_close`)

Read the file completely. Identify:
- All public classes and methods
- Input parameters and their types
- Return values and their types
- Error conditions and how they are handled
- Any calls to `processing.run()` or `safe_processing_run()` — these determine the tier (see Step 3)
- Whether the module has a `debug_mode` parameter

## Step 2 — Check for existing tests

Search `test/` for an existing test file for `$ARGUMENTS`:
- `test/test_$ARGUMENTS.py` (snake_case variant)
- Any file matching `test_*$ARGUMENTS*`

If a test file **exists**: extend it, do not replace it.
If no test file exists: create `test/test_<snake_case_name>.py`.

Also check `docs/test-strategy.md` §6 (Module-to-Test Mapping) to understand the current test count and documented gaps for this module.

## Step 3 — Consult project rules (mandatory)

Read **all** of these files before writing any code:

1. `docs/test-strategy.md` — **authoritative reference**: tier definitions, coverage targets, module mapping, gap backlog, edge case catalog, fixture scope rules
2. `ai/core/testing-rules.md` — tactical rules: geometry checks, structure, framework
3. `ai/core/qgis-api-rules.md` — QGIS API compatibility rules
4. `ai/domain/geometry-validation.md` — null/empty/validity check patterns

Also read:
- `test/utilities.py` — QGIS app initialisation helper
- `test/layer_factories.py` — shared factory functions (import AFTER `get_qgis_app()`)

For an example of a well-structured test file, read `test/test_blocker.py`.

If the module under test is in `ibtool_tools/CreateMST.py`, `helpers/mst_utils.py`, or `ibtool_tools/MST_Clustering.py`, also read `ai/domain/mst-testing.md`.

## Step 4 — Write the test file

### Tier decision (from `docs/test-strategy.md` §2.2 and §3)

```
Does the function under test call processing.run()?
├── No  → @pytest.mark.unit
└── Yes → @pytest.mark.integration  (requires Docker / local QGIS)

Is this a boundary or degenerate input?
└── Yes → additionally add @pytest.mark.edge_case

Will the test use >50 features or measure time/memory?
└── Yes → additionally add @pytest.mark.performance AND @pytest.mark.slow
```

### Required structure

```python
import pytest
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsCoordinateReferenceSystem, QgsPointXY,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.$ARGUMENTS import <function_or_class>


class Test$ARGUMENTS:
    """Tests for <module_name>.<function_or_class>."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)

    # --- domain-specific helpers (only if not covered by conftest factories) ---

    # --- tests ---

    @pytest.mark.unit          # or @pytest.mark.integration
    def test_normal_case(self):
        """<Imperative description of what this test verifies.>"""
        ...
```

**Important:** Import shared factories from `layer_factories.py` instead of defining local equivalents. Only define local helpers for domain-specific geometry layouts (e.g. `_make_two_block_layer()`). The import must come AFTER `get_qgis_app()` — never before, and never from `conftest.py`.

**QgsVectorLayer scope:** Always create layers inside test methods, never at class level. Layers are mutable — sharing them across tests causes interference (see `docs/test-strategy.md` §5.2).

### Required geometry assertions (mandatory after every geometry operation)

```python
assert result_layer is not None
assert result_layer.featureCount() > 0          # or == expected_count
for feat in result_layer.getFeatures():
    geom = feat.geometry()
    assert not geom.isNull(),   "Geometry must not be null"
    assert not geom.isEmpty(),  "Geometry must not be empty"
    assert geom.isGeosValid(),  "Geometry must be GEOS-valid"
```

### Mandatory test cases (minimum)

1. **Normal case** — valid input; check return value, feature count, geometry validity
2. **Empty input layer** — 0 features; verify graceful handling (no crash, defined return)
3. **Null geometry on one feature** — layer with one null-geometry feature; verify no crash
4. At least one **domain-specific edge case** (`@pytest.mark.edge_case`) from this catalog:
   - Layer with 0 features after filtering
   - Mismatched CRS between inputs
   - Multipart geometry where singlepart is expected
   - Partition ID `-1` (unassigned features in Blocker output)

### debug_mode invariant (mandatory if the module has debug_mode)

If the module accepts a `debug_mode` parameter, add this test:

```python
@pytest.mark.integration
def test_debug_mode_does_not_change_result(self, tmp_path):
    """Debug mode produces same feature count as non-debug mode."""
    result_normal = tool_function(sample_layer, debug_mode=False)
    result_debug  = tool_function(sample_layer, debug_mode=True,
                                  workspace_path=str(tmp_path))
    assert result_debug.featureCount() == result_normal.featureCount()
```

### Docstring rule (mandatory)

Every test method must have a one-line docstring in the imperative mood:

```python
def test_gap_is_closed_when_below_threshold(self):
    """Closes gaps smaller than the threshold distance."""
```

## Step 5 — Run pylint

Run pylint on the test file and on the module under test:

```bash
pylint test/test_<module_name>.py ibtool/ibtool_tools/<ModuleName>.py
```

Fix any warnings introduced by your changes. The pylint score must not decrease compared to the project baseline (9.98/10).

## Step 6 — Output

Report:
1. Path of the created/modified test file
2. List of test methods written and what each covers
3. Which tier markers were applied and why
4. Whether the `debug_mode` invariant was tested
5. Any assumptions made about expected behavior (if the module's behavior was unclear)
