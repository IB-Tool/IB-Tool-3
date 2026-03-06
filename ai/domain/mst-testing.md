# MST Testing

Test documentation for the MST (Minimum Spanning Tree) functionality.

## Test Files

| File | Type | Content |
|------|------|---------|
| `test_fixtures_mst.py` | Fixtures | `MSTTestFixtures` class with reusable test data and validation helpers |
| `test_create_mst.py` | Integration | End-to-end MST generation, input validation, CRS handling (12 tests) |
| `test_mst_components.py` | Unit | Helper functions: `unique()`, `create_layer_from_edges()`, `polygon_stuetzpunkte_dict()` (12 tests) |
| `test_mst_modules.py` | Modular | Refactored classes: `DelaunayProcessor`, `StreetProcessor`, `MSTCalculator`, data classes (17 tests) |
| `test_mst_performance_edge_cases.py` | Performance | Scaling, memory usage, edge cases: empty inputs, invalid geometries (13 tests) |

**Support files**: `run_mst_tests.py` (test runner), `pytest_mst.ini` (configuration)

## Test Execution

```bash
# All MST tests
python test/run_mst_tests.py
python test/run_mst_tests.py integration|unit|modules|performance

# With pytest directly
pytest test/test_*mst*.py test/test_create_mst.py -v
pytest test/test_create_mst.py -v --tb=short

# Coverage
pytest test/test_create_mst.py --cov=ibtool.ibtool_tools.CreateMST --cov-report=html
pytest test/test_*mst*.py --cov=ibtool.ibtool_tools --cov-branch --cov-report=term-missing

# Skip slow tests
pytest test/test_create_mst.py -m "not slow"

# Debugging
pytest test/test_create_mst.py::TestCreateMST::test_calculate_mst_with_simple_buildings -vvs
pytest test/test_create_mst.py --log-cli-level=DEBUG
pytest test/test_create_mst.py --pdb
```

## Pytest Markers

| Marker | Meaning |
|--------|---------|
| `@pytest.mark.integration` | End-to-end tests |
| `@pytest.mark.unit` | Individual functions |
| `@pytest.mark.performance` | Scaling tests |
| `@pytest.mark.edge_case` | Boundary conditions |
| `@pytest.mark.modular` | Modular components |
| `@pytest.mark.slow` | Tests >5 seconds |

## Test Fixtures

| Fixture | Description |
|---------|------------|
| Simple Building Layout | 4 rectangular buildings in a grid pattern |
| Complex Building Layout | Various shapes and sizes |
| Simple Street Network | Connected street segments |
| Large Datasets | Generated buildings/streets for performance testing |

**Expected MST properties** (4-building test case):
- 3 edges (n-1 for n buildings)
- All edge weights > 0
- Minimum total distance

## Performance Benchmarks

| Dataset | Buildings | Expected Time | Memory |
|---------|-----------|---------------|--------|
| Small | 4 | <1s | <10MB |
| Medium | 25 | <5s | <25MB |
| Large | 100 | <30s | <100MB |

## Known Issues

### calculate_mst() returns None

**Cause**: Missing dependencies (scipy, networkx, numpy) or QGIS Processing not initialized.

**Solution**: Tests use defensive programming:
```python
result = calculate_mst(building_layer, street_layer, crs)
if result is None:
    pytest.skip("MST calculation returned None - likely missing dependencies")
```

### Function Signature

Current signature of `calculate_mst()`:
```python
def calculate_mst(input_bdg, streets_orig, SpatialReference, road_length=50)
```

## Coverage Goals

- **Overall MST**: >90%
- **Core algorithms**: >95%
- **Helper functions**: >85%
- **Error handling**: >80%
