# MST Module Architecture

Status: Monolithisch — Refactoring geplant.

## Aktueller Zustand

`CreateMST.py` ist eine monolithische 372-Zeilen-Funktion:

- Einzelne große `calculate_mst()`-Funktion mit eingebetteten Hilfsfunktionen
- Delaunay-Triangulation, Straßenverarbeitung und MST-Berechnung an einer Stelle
- Komplexe verschachtelte Operationen ohne klare Trennung der Zuständigkeiten
- Konstanten inline definiert (`road_length=50`, `buffer_distance=5`, `coordinate_tolerance=0.0001`)

## Ziel-Architektur

```
ibtool/ibtool_tools/mst/     # Modulare Zielstruktur
├── __init__.py
├── delaunay_processor.py    # Delaunay-Triangulationsoperationen
├── street_processor.py     # Straßenfilterung und Knoten-Erkennung
├── mst_calculator.py       # Graph-Operationen und MST-Berechnung
├── mst_data_classes.py     # Datenstrukturen für MST-Verarbeitung
└── create_mst.py           # Orchestrator-Klasse
```

## Design-Prinzipien für Refactoring

- Jeder Processor besitzt seine Business-Logic-Parameter als Klassenkonstanten
- Keine geteilten Config-Objekte — einfache Konstruktoren ohne Parameter
- QGIS-technische Parameter zentralisiert in `helpers/qgis_defaults.py`
- Klare Trennung: Geometrie vs. Straßen vs. Graph-Algorithmen
- Rückwärtskompatibilität durch einfache Wrapper-Funktionen

## Algorithmus-Übersicht

1. **Delaunay-Triangulation**: Erzeugt Verbindungsnetz zwischen Gebäude-Schwerpunkten
2. **Straßenverarbeitung**: Filtert kurze Straßensegmente, erkennt Knoten
3. **Graph-Aufbau**: Erstellt gewichteten Graphen aus Delaunay-Kanten
4. **MST-Berechnung**: Berechnet minimalen Spannbaum (Kruskal/Prim)
5. **Kantenfilterung**: Entfernt Kanten die Straßen kreuzen
