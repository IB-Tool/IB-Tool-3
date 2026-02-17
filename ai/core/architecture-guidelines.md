# Architecture Guidelines

Leitlinien für Architektur-Entscheidungen im IBTool-Projekt.

## Parameter Management

- **Avoid over-engineering**: Nur separate Config-Dateien wenn Parameter modulübergreifend geteilt werden
- **Lokale Parameter lokal halten**: Business-Logic-Parameter als Klassenkonstanten definieren wo sie genutzt werden
- **YAGNI**: Keine Abstraktionen bis sie tatsächlich gebraucht werden (2-3 Parameter rechtfertigen keine Config-Klasse)
- **`helpers/qgis_defaults.py`**: Für technische QGIS-Parameter (Buffer-Settings, Precision) die tool-übergreifend konsistent sein müssen
- **Single Source of Truth**: Jeder Parameter wird an genau einer Stelle definiert

## Klassen-Design

- **Komposition vor Vererbung**: Spezialisierte Klassen die zusammenarbeiten statt komplexer Vererbungshierarchien
- **Klare Verantwortlichkeiten**: Jede Klasse hat genau einen Zweck
- **Minimale Konstruktoren**: Config-Objekte nur wenn wirklich nötig — einfache Initialisierung bevorzugen
- **Konstanten als Klassenattribute**: `CLASS_CONSTANT = value` für Parameter die nur innerhalb dieser Klasse genutzt werden

## Code-Organisation

- **Modulare Architektur**: Große Funktionen (500+ Zeilen) in spezialisierte Klassen mit fokussierten Methoden aufteilen
- **Keine Magic Numbers**: Alle numerischen Konstanten benennen und dokumentieren
- **Redundanz eliminieren**: Wenn ein Parameter an mehreren Stellen auftaucht — ist er wirklich geteilt oder nur dupliziert?
- **Pragmatisches Refactoring**: Immer fragen "Dient diese Komplexität einem realen Zweck?" bevor Abstraktionen eingeführt werden

## Datei-Organisation

- **Verwandte Funktionalität gruppieren**: Modul-Verzeichnisse (wie `mst/`) für komplexe Algorithmen
- **Globale Utilities in `helpers/`**: Technische Parameter, Logging, Geometrie-Utils
- **Config-Proliferation vermeiden**: Keine multiplen Config-Dateien für verschiedene Zwecke

## Usage Patterns

**QGIS-Operationen:**
```python
from helpers.qgis_defaults import QGISDefaults

qgis_defaults = QGISDefaults()
buffer_result = processing.run("native:buffer", {
    'SEGMENTS': qgis_defaults.buffer_segments,
    'END_CAP_STYLE': qgis_defaults.buffer_end_cap_style,
})
```

**Algorithmus-spezifische Parameter:**
```python
class StreetProcessor:
    ROAD_LENGTH_THRESHOLD = 50.0  # Business logic parameter

    def filter_short_streets(self, streets):
        expression = f'"length" < {self.ROAD_LENGTH_THRESHOLD}'
```

**Modulare Verarbeitung:**
```python
# Einfache Initialisierung — keine Config-Objekte nötig
processor = StreetProcessor()
calculator = MSTCalculator()

# Saubere Workflow-Orchestrierung
mst_creator = CreateMST()
result = mst_creator.calculate_mst(buildings, streets, crs)
```
