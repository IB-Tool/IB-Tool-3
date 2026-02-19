---
description: Use this skill when the user asks to write, create, or add tests for a module, function, or class — for example "schreib Tests für GapClose", "write tests for the blocker", "add test coverage for X", "fehlende Tests ergänzen". Invoke automatically whenever a testing task is identified for this QGIS plugin project.
---

# /write-tests — Write Tests for an IBTool Module

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
- Any calls to `processing.run()` or `safe_processing_run()`

## Step 2 — Check for existing tests

Search `test/` for an existing test file for `$ARGUMENTS`:
- `test/test_$ARGUMENTS.py` (snake_case variant)
- Any file matching `test_*$ARGUMENTS*`

If a test file **exists**: extend it, do not replace it.
If no test file exists: create `test/test_<snake_case_name>.py`.

## Step 3 — Consult project rules (mandatory)

Read these three files before writing any code:
- `ai/core/testing-rules.md`
- `ai/core/qgis-api-rules.md`
- `ai/domain/geometry-validation.md`

Also read `test/utilities.py` and `test/conftest.py` to understand the QGIS setup.

For an example of a well-structured test file, read `test/test_blocker.py`.

## Step 4 — Write the test file

### Required structure

```python
import pytest
from unittest.mock import Mock, patch
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField,
    QgsCoordinateReferenceSystem, QgsPointXY
)
from PyQt5.QtCore import QVariant
from test.utilities import get_qgis_app

# Import the module under test (adjust path as needed)
from ibtool.ibtool_tools.$ARGUMENTS import ...


class Test$ARGUMENTS:

    @classmethod
    def setup_class(cls):
        cls.qgis_app, cls.canvas, cls.iface, cls.parent = get_qgis_app()

    # --- Fixtures ---

    @staticmethod
    def _create_test_layer(crs_epsg: str = "EPSG:25833") -> QgsVectorLayer:
        """Create a minimal in-memory polygon layer for testing."""
        layer = QgsVectorLayer(f"Polygon?crs={crs_epsg}", "test_layer", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("id", QVariant.Int),
        ])
        layer.updateFields()
        assert layer.isValid(), "Test layer must be valid"
        return layer

    # --- Tests ---

    def test_normal_case(self):
        """Test standard behavior with valid input."""
        ...

    def test_empty_input(self):
        """Test behavior when input layer has no features."""
        ...

    def test_invalid_geometry(self):
        """Test behavior with null or invalid geometry."""
        ...
```

### Required geometry assertions

Always assert after any geometry operation:
```python
assert not geom.isNull(), "Geometry must not be null"
assert not geom.isEmpty(), "Geometry must not be empty"
assert geom.isGeosValid(), "Geometry must be GEOS-valid"
```

### Required pytest markers

- `@pytest.mark.integration` — tests that run QGIS Processing algorithms
- `@pytest.mark.unit` — tests for pure Python logic without Processing
- `@pytest.mark.slow` — tests that take more than 5 seconds
- `@pytest.mark.edge_case` — empty input, null geometry, zero features

### Mandatory test cases (minimum)

1. **Normal case** — valid input, check output is not None, geometry is valid
2. **Empty layer** — input with 0 features, verify graceful handling (no crash)
3. **Invalid/null geometry** — at least one feature with null geometry, verify no crash
4. At least one **edge case** relevant to the module's domain logic

## Step 5 — Output

Report:
1. Path of the created/modified test file
2. List of test methods written and what each covers
3. Which test markers were applied and why
4. Any assumptions made about expected behavior (if the module's behavior was unclear)
