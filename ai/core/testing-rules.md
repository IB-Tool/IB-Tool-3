# Testing Rules

> For the full test strategy — tier definitions, coverage targets, module mapping, and gap backlog — see [`docs/test-strategy.md`](../../docs/test-strategy.md). This file contains the tactical rules (geometry checks, framework, structure) that apply to every test.

## Before Every Code Change

1. **Understand existing logic**: Read the relevant code before making changes
2. **Run tests**: Existing tests must pass before and after the change
3. **No regression**: No existing functionality may break due to changes

## Test Framework

- **pytest** as the test framework
- Tests reside in `test/` following the pattern `test_*.py`
- `conftest.py` configures the test environment (sys.path, QGIS initialization)
- Docker environment for consistent QGIS test execution

## Test Execution

```bash
# Docker (recommended — consistent environment)
docker build -t qgis-plugin-test .
docker run --rm qgis-plugin-test

# Local (requires QGIS installation)
pytest test/ -v

# Single test
pytest test/test_blocker.py -v
```

## Testing Geometry Operations

Include the following checks for every geometry operation:

### Validity Check

```python
result_geom = result_feature.geometry()
assert not result_geom.isNull(), "Geometry must not be null"
assert not result_geom.isEmpty(), "Geometry must not be empty"
assert result_geom.isGeosValid(), "Geometry must be valid"
```

### Multipart Check

```python
# Verify expected geometry type
if expect_singlepart:
    assert not result_geom.isMultipart(), "Expected singlepart geometry"
```

### Feature Count

```python
# Ensure features are not lost
assert result_layer.featureCount() > 0, "Result must contain features"
```

## Error Messages

- **Never silently swallow errors**: Every expected exception must be tested
- Test that error messages are meaningful
- Test edge cases: empty layers, None geometries, wrong CRS

## Test Structure

```python
class TestToolName:
    """Tests for the ToolName module."""

    def test_normal_case(self, sample_layer):
        """Standard case with valid inputs."""
        result = tool_function(sample_layer)
        assert result is not None

    def test_empty_input(self):
        """Behavior with empty input layer."""
        # Expect defined behavior, not a crash

    def test_invalid_geometry(self, invalid_layer):
        """Behavior with invalid geometry."""
        # Expect error message or automatic correction
```

## Coverage

- New features must be covered by tests
- Coverage reports via `pytest --cov=. --cov-report=html`
- CI pipeline checks tests automatically on every push
