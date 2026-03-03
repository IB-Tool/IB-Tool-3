# Input Data

## Overview

| Layer | Role |
|-------|------|
| **HU** — Building Footprints | Building outlines used for filtering, density analysis, and boundary generation |
| **RN** — Road Network | Road network used to derive street blocks and to snap boundaries |
| **Part** — Partitioning | Polygons that divide the study area into processing units |
| **Aux** — Auxiliary Layer | Additional line/polygon barriers merged with the road network |
| **Filter File** | `.txt` file defining positive and negative ATKIS function-code filters |

---

## General Rules

- All layers must use the same **Coordinate Reference System (CRS)**. The CRS is set in the plugin interface (e.g. `EPSG:25832`).
- All layers must be loadable as valid QGIS vector layers (`.shp` or `.gpkg`).
- No layer may be empty (0 features).
- Line layers (RN, Aux) must not contain **multipart geometries**. Dissolve with `native:multiparttosingleparts` if needed.

---

## Layer Specifications

### HU — Building Footprints

| Property | Requirement |
|----------|-------------|
| Geometry type | **Polygon** |
| Minimum features | 50 |
| Required field | `fkt`, `gfkzshh`, or `funktion` — ATKIS building function code (e.g. `31001_1000`). Only the first 10 characters are used for filter matching. |

### RN — Road Network

| Property | Requirement |
|----------|-------------|
| Geometry type | **LineString** |
| Minimum features | 30 |
| Multipart | Not supported — use single-part geometries |

Road segments shorter than 50 m (dead ends) are filtered automatically during MST calculation. A `length` field is not required.

### Part — Partitioning

| Property | Requirement |
|----------|-------------|
| Geometry type | **Polygon** |
| Required field | `NAME` — partition label (e.g. `PART_123`) |
| Name format | `PART_<number>` (e.g. `PART_36`, `PART_433`) |
| Part:HU ratio | Should not exceed 1:10,000. Too few partitions leads to very long per-partition runtimes. |

The partitioning defines independent processing units. In the plugin interface a subset can be specified by partition name list or start/end range.

### Aux — Auxiliary Layer

| Property | Requirement |
|----------|-------------|
| Geometry type | Polygon or LineString |
| Minimum features | 10 |

The Aux layer is merged with RN and used to refine block derivation (e.g. additional barriers or boundaries).

### Filter File

| Property | Requirement |
|----------|-------------|
| File format | Plain text (`.txt`) |
| Encoding | UTF-8 |
| Required sections | `#Filter positive` and `#Filter negative` (in that order) |

Controls which buildings are included or excluded. Format:

```
#Filter positive
31001_1000, Wohngeb
31001_1010, Wohnhaus
31001_1100, GemischtesWohnen
...

#Filter negative
31001_1310, Freizeit
31001_2600, Entsorgung
31001_2720, GebLandForst
...
```

- Lines starting with `#` are section headers or comments; blank lines are ignored.
- Only the **first 10 characters** of each entry are matched against the `fkt`/`funktion` field.
- **Positive filter**: only buildings whose code matches an entry are retained.
- **Negative filter**: buildings whose code matches an entry are excluded.

### Output and Working Paths

| Property | Requirement |
|----------|-------------|
| Output file | Path for the result GeoPackage (`.gpkg`). The parent directory must exist. |
| Working directory | Path for intermediate files. Parent directory must exist; the directory itself is created during processing. |

---

## Validation Checks

The **Check** button in the dialog runs all checks before processing. Critical errors block the **Start** button; warnings are informational.

| Check | Type | Description |
|-------|------|-------------|
| File paths | Error | All paths must be specified and exist |
| Layer loadability | Error | Files must be loadable as valid QGIS layers |
| Empty layers | Error | Layers must not be empty (0 features) |
| Minimum features HU | Error | At least 50 features required |
| Minimum features RN | Error | At least 30 features required |
| Minimum features Aux | Error | At least 10 features required |
| CRS match | Error | All layers must use the CRS selected in the UI |
| HU geometry type | Error | Must be polygon geometry |
| HU required field | Error | Field `fkt`, `gfkzshh`, or `funktion` must be present |
| RN geometry type | Error | Must be line geometry |
| Multipart geometries | Warning | Line layers should not contain multipart geometries |
| Part required field | Error | Field `NAME` must be present |
| Part name format | Error | NAME values must match the `PART_<number>` pattern |
| Part:HU ratio | Warning | Ratio of HU to Part should not exceed 1:10,000 |
| Filter file format | Error | Sections `#Filter positive` and `#Filter negative` required |
| Output paths | Error | Output and working directories must exist |
