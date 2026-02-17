# Constraints

Verbindliche Regeln für alle Code-Änderungen im IBTool-Projekt.

## Interface-Zugriff

- **Kein direkter Zugriff auf `iface`** außerhalb der Hauptklasse (`ibtool/ibtool.py`) und des Dialogs (`ibtool_dialog.py`)
- Processing-Tools (`ibtool_tools/`) erhalten niemals `iface` als Parameter
- Tools kommunizieren Ergebnisse über Rückgabewerte, nicht über UI-Aufrufe

## Variablen und Zustand

- **Keine globalen Variablen** — alle Zustände werden als Parameter übergeben oder sind Klassenattribute
- Processing-Tools müssen **zustandslos** (stateless) sein
- Keine Seiteneffekte außerhalb des definierten Scopes einer Funktion
- Keine Modifikation von Eingabeparametern (Input-Layer, Feature-Listen)

## Dokumentation

- **Jede neue Funktion** erhält einen Google-style Docstring
- **Jede neue Klasse** erhält einen Docstring mit Zweckbeschreibung
- Parameter mit nicht-offensichtlicher Bedeutung werden im Docstring erklärt

## Pfade und Konfiguration

- **Keine hardcodierten Pfade** — alle Pfade über Parameter oder `config_manager.py`
- Workspace-Pfad wird vom Benutzer über die UI gesetzt
- Temporäre Dateien über `QgsProcessing.TEMPORARY_OUTPUT`

## Dependencies

- **Keine neuen Abhängigkeiten** ohne vorherige Abstimmung
- Erlaubte Bibliotheken: numpy, scipy, sklearn, networkx, pandas, matplotlib, geopandas, shapely
- QGIS-eigene Module (qgis.core, qgis.analysis, processing) unbeschränkt nutzbar

## Numerische Werte

- **Keine Magic Numbers** — alle Konstanten benennen und dokumentieren
- Algorithmus-spezifische Parameter als Klassenkonstanten definieren
- QGIS-technische Parameter in `helpers/qgis_defaults.py` zentralisieren

## Fehlerbehandlung

- Jede `processing.run()`-Operation muss Fehler abfangen
- Kritische Fehler loggen und Verarbeitung abbrechen
- Warnungen loggen und wenn möglich weitermachen
- Im Debug-Modus Zwischenergebnisse speichern

## Strings

- Alle benutzersichtbaren Strings über `QCoreApplication.translate()` übersetzbar machen
- Interne Log-Nachrichten dürfen auf Englisch oder Deutsch sein
