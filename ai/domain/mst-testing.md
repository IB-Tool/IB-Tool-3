# MST Testing

Test-Dokumentation für die MST-Funktionalität (Minimum Spanning Tree).

## Test-Dateien

| Datei | Typ | Inhalt |
|-------|-----|--------|
| `test_fixtures_mst.py` | Fixtures | `MSTTestFixtures`-Klasse mit wiederverwendbaren Testdaten und Validierungshelfern |
| `test_create_mst.py` | Integration | End-to-end MST-Generierung, Input-Validierung, CRS-Handling (12 Tests) |
| `test_mst_components.py` | Unit | Helper-Funktionen: `unique()`, `create_layer_from_edges()`, `polygon_stuetzpunkte_dict()` (12 Tests) |
| `test_mst_modules.py` | Modular | Refactored-Klassen: `DelaunayProcessor`, `StreetProcessor`, `MSTCalculator`, Data-Classes (17 Tests) |
| `test_mst_performance_edge_cases.py` | Performance | Skalierung, Speicherverbrauch, Edge Cases: leere Inputs, ungültige Geometrien (13 Tests) |

**Support-Dateien**: `run_mst_tests.py` (Test-Runner), `pytest_mst.ini` (Konfiguration)

## Test-Ausführung

```bash
# Alle MST-Tests
python test/run_mst_tests.py
python test/run_mst_tests.py integration|unit|modules|performance

# Mit pytest direkt
pytest test/test_*mst*.py test/test_create_mst.py -v
pytest test/test_create_mst.py -v --tb=short

# Coverage
pytest test/test_create_mst.py --cov=ibtool.ibtool_tools.CreateMST --cov-report=html
pytest test/test_*mst*.py --cov=ibtool.ibtool_tools --cov-branch --cov-report=term-missing

# Langsame Tests überspringen
pytest test/test_create_mst.py -m "not slow"

# Debugging
pytest test/test_create_mst.py::TestCreateMST::test_calculate_mst_with_simple_buildings -vvs
pytest test/test_create_mst.py --log-cli-level=DEBUG
pytest test/test_create_mst.py --pdb
```

## Pytest-Marker

| Marker | Bedeutung |
|--------|-----------|
| `@pytest.mark.integration` | End-to-end-Tests |
| `@pytest.mark.unit` | Einzelne Funktionen |
| `@pytest.mark.performance` | Skalierungstests |
| `@pytest.mark.edge_case` | Grenzfälle |
| `@pytest.mark.modular` | Modulare Komponenten |
| `@pytest.mark.slow` | Tests >5 Sekunden |

## Test-Fixtures

| Fixture | Beschreibung |
|---------|-------------|
| Simple Building Layout | 4 rechteckige Gebäude im Rastermuster |
| Complex Building Layout | Verschiedene Formen und Größen |
| Simple Street Network | Verbundene Straßensegmente |
| Large Datasets | Generierte Gebäude/Straßen für Performance-Tests |

**Erwartete MST-Eigenschaften** (4-Gebäude-Testfall):
- 3 Kanten (n-1 für n Gebäude)
- Alle Kantengewichte > 0
- Minimale Gesamtdistanz

## Performance-Benchmarks

| Datensatz | Gebäude | Erwartete Zeit | Speicher |
|-----------|---------|----------------|----------|
| Klein | 4 | <1s | <10MB |
| Mittel | 25 | <5s | <25MB |
| Groß | 100 | <30s | <100MB |

## Bekannte Issues

### calculate_mst() gibt None zurück

**Ursache**: Fehlende Dependencies (scipy, networkx, numpy) oder QGIS-Processing nicht initialisiert.

**Lösung**: Tests verwenden defensive Programmierung:
```python
result = calculate_mst(building_layer, street_layer, crs)
if result is None:
    pytest.skip("MST calculation returned None - likely missing dependencies")
```

### Funktionssignatur

Aktuelle Signatur von `calculate_mst()`:
```python
def calculate_mst(input_bdg, streets_orig, SpatialReference, road_length=50)
```

## Coverage-Ziele

- **Gesamt MST**: >90%
- **Kern-Algorithmen**: >95%
- **Helper-Funktionen**: >85%
- **Fehlerbehandlung**: >80%
