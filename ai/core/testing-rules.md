# Testing Rules

## Vor jeder Code-Änderung

1. **Bestehende Logik verstehen**: Relevanten Code lesen, bevor Änderungen gemacht werden
2. **Tests ausführen**: Bestehende Tests müssen vor und nach der Änderung grün sein
3. **Keine Regression**: Keine bestehende Funktionalität darf durch Änderungen brechen

## Test-Framework

- **pytest** als Test-Framework
- Tests liegen in `test/` mit dem Muster `test_*.py`
- `conftest.py` konfiguriert die Testumgebung (sys.path, QGIS-Initialisierung)
- Docker-Umgebung für konsistente QGIS-Testausführung

## Test-Ausführung

```bash
# Docker (empfohlen — konsistente Umgebung)
docker build -t qgis-plugin-test .
docker run --rm qgis-plugin-test

# Lokal (erfordert QGIS-Installation)
pytest test/ -v

# Einzelner Test
pytest test/test_blocker.py -v
```

## Geometrie-Operationen testen

Bei jeder Geometrieoperation folgende Prüfungen einbauen:

### Validitätsprüfung

```python
result_geom = result_feature.geometry()
assert not result_geom.isNull(), "Geometry must not be null"
assert not result_geom.isEmpty(), "Geometry must not be empty"
assert result_geom.isGeosValid(), "Geometry must be valid"
```

### Multipart-Check

```python
# Prüfe erwarteten Geometrietyp
if expect_singlepart:
    assert not result_geom.isMultipart(), "Expected singlepart geometry"
```

### Feature-Count

```python
# Stelle sicher, dass Features nicht verloren gehen
assert result_layer.featureCount() > 0, "Result must contain features"
```

## Fehlermeldungen

- **Niemals stillschweigend verschlucken**: Jede erwartete Exception muss getestet werden
- Teste, dass Fehlermeldungen aussagekräftig sind
- Teste Edge Cases: leere Layer, None-Geometrien, falsche CRS

## Test-Struktur

```python
class TestToolName:
    """Tests für ToolName-Modul."""

    def test_normal_case(self, sample_layer):
        """Standardfall mit gültigen Eingaben."""
        result = tool_function(sample_layer)
        assert result is not None

    def test_empty_input(self):
        """Verhalten bei leerem Input-Layer."""
        # Erwarte definiertes Verhalten, nicht Absturz

    def test_invalid_geometry(self, invalid_layer):
        """Verhalten bei ungültiger Geometrie."""
        # Erwarte Fehlermeldung oder automatische Korrektur
```

## Coverage

- Neue Features müssen mit Tests abgedeckt sein
- Coverage-Reports via `pytest --cov=. --cov-report=html`
- CI-Pipeline prüft Tests automatisch bei jedem Push
