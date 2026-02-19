# Naming Conventions

## Python Identifiers

| Element | Convention | Example |
|---------|-----------|---------|
| Functions | `snake_case` | `calculate_mst()`, `filter_short_streets()` |
| Methods | `snake_case` | `layer.get_features()` |
| Classes | `PascalCase` | `StreetProcessor`, `DelaunayProcessor` |
| Class constants | `UPPER_SNAKE_CASE` | `ROAD_LENGTH_THRESHOLD = 50.0` |
| Local variables | `snake_case` | `feature_count`, `buffer_result` |
| Modules | `snake_case` | `geometry_utils.py`, `data_loader.py` |
| Tool modules | `PascalCase` | `GapClose.py`, `CreateMST.py` (historical) |
| Packages | `snake_case` | `helpers`, `ibtool_tools` |

## Allowed Abbreviations

These abbreviations are established and may be used without further explanation:

| Abbreviation | Meaning |
|-------------|---------|
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

All other terms must be spelled out.

## Layer Names

- Unique and descriptive: `"dissolved_buildings"`, not `"temp1"`
- For temporary intermediate layers: prefix with processing step, e.g. `"buffered_streets"`
- For final results: use domain terminology, e.g. `"settlement_boundary"`

## File Names

| Type | Convention | Example |
|------|-----------|---------|
| Helper modules | `snake_case.py` | `geometry_utils.py` |
| Tool modules | `PascalCase.py` | `GapClose.py` |
| Test modules | `test_*.py` | `test_blocker.py` |
| Configuration | `snake_case.*` | `qgis_defaults.py` |
| Documentation | `kebab-case.md` | `plugin-architecture.md` |

## Parameter Names

- Descriptive, not generic: `buffer_distance` instead of `dist`
- Include unit in name when not obvious: `tolerance_meters`
- Boolean variables as questions: `is_valid`, `has_geometry`, `debug_mode`
