# Naming Conventions

## Python-Bezeichner

| Element | Konvention | Beispiel |
|---------|-----------|----------|
| Funktionen | `snake_case` | `calculate_mst()`, `filter_short_streets()` |
| Methoden | `snake_case` | `layer.get_features()` |
| Klassen | `PascalCase` | `StreetProcessor`, `DelaunayProcessor` |
| Klassenkonstanten | `UPPER_SNAKE_CASE` | `ROAD_LENGTH_THRESHOLD = 50.0` |
| Lokale Variablen | `snake_case` | `feature_count`, `buffer_result` |
| Module | `snake_case` | `geometry_utils.py`, `data_loader.py` |
| Tool-Module | `PascalCase` | `GapClose.py`, `CreateMST.py` (historisch) |
| Packages | `snake_case` | `helpers`, `ibtool_tools` |

## Erlaubte Abkürzungen

Diese Abkürzungen sind etabliert und dürfen ohne weitere Erklärung verwendet werden:

| Abkürzung | Bedeutung |
|-----------|-----------|
| `id` | Identifier |
| `crs` | Coordinate Reference System |
| `geom` | Geometry |
| `mst` | Minimum Spanning Tree |
| `hu` | Hausumringe (Building Footprints) |
| `rn` | Road Network |
| `aux` | Auxiliary |
| `part` | Partition |
| `wkt` | Well-Known Text |
| `wkb` | Well-Known Binary |

Alle anderen Begriffe ausschreiben.

## Layer-Namen

- Eindeutig und beschreibend: `"dissolved_buildings"`, nicht `"temp1"`
- Für temporäre Zwischenlayer: Präfix mit Arbeitsschritt, z.B. `"buffered_streets"`
- Für Endresultate: Fachbegriff verwenden, z.B. `"settlement_boundary"`

## Dateinamen

| Typ | Konvention | Beispiel |
|-----|-----------|----------|
| Helper-Module | `snake_case.py` | `geometry_utils.py` |
| Tool-Module | `PascalCase.py` | `GapClose.py` |
| Test-Module | `test_*.py` | `test_blocker.py` |
| Konfiguration | `snake_case.*` | `qgis_defaults.py` |
| Dokumentation | `kebab-case.md` | `plugin-architecture.md` |

## Parameter-Namen

- Beschreibend, nicht generisch: `buffer_distance` statt `dist`
- Einheit im Namen wenn nicht offensichtlich: `tolerance_meters`
- Boolean-Variablen als Frage: `is_valid`, `has_geometry`, `debug_mode`
