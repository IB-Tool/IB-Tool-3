# New Feature Task Template

## Purpose

Vorlage für die Implementierung neuer Funktionalität im IBTool-Projekt. Ziel: saubere Integration ohne bestehende Funktionalität zu beeinträchtigen.

## Scope

- Neues Feature klar kapseln
- Bestehende API nicht brechen
- Dokumentation ergänzen
- Tests für neues Feature schreiben

## Vorgehensweise

### 1. Anforderungsklärung

- [ ] Feature-Anforderung vollständig verstehen
- [ ] Eingabe- und Ausgabedaten definieren
- [ ] Abgrenzung: was gehört NICHT zum Feature?
- [ ] Abhängigkeiten zu bestehenden Modulen identifizieren

### 2. Architektur

- [ ] Wo im Projektbaum gehört das Feature hin?
- [ ] Neues Tool in `ibtool_tools/`? Neuer Helper in `helpers/`?
- [ ] Schnittstellen zu bestehenden Modulen definieren
- [ ] Parameter festlegen (Klassenkonstanten vs. QGIS-Defaults)

### 3. Implementierung

- [ ] Modul mit klarer Verantwortung erstellen
- [ ] Stateless Processing-Funktion (Eingabe → Ausgabe)
- [ ] Logging über Logger-System
- [ ] Fehlerbehandlung mit `safe_processing_run()`
- [ ] Debug-Modus-Unterstützung (`_dbg`-Dict)

### 4. Integration

- [ ] Import in `ibtool/ibtool.py` (absolute Imports)
- [ ] UI-Anbindung im Dialog falls nötig
- [ ] Logging-Nachrichten für Fortschritt und Fehler

### 5. Validierung

- [ ] Unit-Tests für das neue Modul
- [ ] Integrationstests im Gesamtworkflow
- [ ] Bestehende Tests unverändert grün
- [ ] Geometrie-Validierung in Tests

### 6. Dokumentation

- [ ] Docstrings für alle neuen Funktionen/Klassen
- [ ] CHANGELOG.md aktualisieren
- [ ] CLAUDE.md aktualisieren falls Architektur sich ändert

## Allowed Changes

- Neues Modul in `ibtool_tools/` oder `helpers/`
- Import des neuen Moduls in `ibtool/ibtool.py`
- UI-Erweiterung im Dialog (neue Widgets, Tabs)
- Neue Testdatei in `test/`
- CHANGELOG- und CLAUDE.md-Aktualisierung

## Forbidden Changes

- Bestehende öffentliche API ändern
- Bestehende Tool-Funktionalität modifizieren
- Neue externe Dependencies ohne Abstimmung
- Bestehende Tests modifizieren (außer Ergänzung)

## Checklist

```
[ ] Anforderung klar definiert
[ ] Architektur-Entscheidung dokumentiert
[ ] Feature sauber gekapselt
[ ] Stateless Processing-Funktion
[ ] Debug-Modus unterstützt
[ ] Unit-Tests geschrieben
[ ] Bestehende Tests grün
[ ] CHANGELOG aktualisiert
[ ] Code-Review-ready
```

## Modul-Vorlage

```python
"""
Modulname — Kurzbeschreibung.

Dieses Modul implementiert [Feature-Beschreibung].
"""

from .helpers.logger import Logger

logger = Logger()


class FeatureName:
    """Beschreibung der Klasse."""

    # Algorithmus-Parameter
    PARAMETER_NAME = 42.0  # Beschreibung und Einheit

    def process(self, input_layer, crs, debug_mode=False, workspace_path=None):
        """Hauptverarbeitungsfunktion.

        Args:
            input_layer: QgsVectorLayer mit Eingabedaten
            crs: QgsCoordinateReferenceSystem
            debug_mode: Debug-Features aktivieren
            workspace_path: Pfad für Debug-Ausgaben

        Returns:
            QgsVectorLayer mit Ergebnis
        """
        _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path,
                     tool_name="FeatureName")
        # Verarbeitung...
```
