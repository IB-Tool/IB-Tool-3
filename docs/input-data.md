# Input Data

This document specifies the five input datasets required by IBTool: geometry types, field requirements, minimum feature counts, and the filter file format. It also lists the complete set of validation checks run by the **Check** button in the dialog.

---

## Overview

| Layer | Role |
|-------|------|
| **HU** — Building Footprints | Building outlines used for filtering, density analysis, and boundary generation |
| **RN** — Road Network | Road network used to derive street blocks and to snap boundaries |
| **Part** — Partitioning | Polygons that divide the study area into processing units |
| **Aux** — Auxiliary Layer | Additional line barriers merged with the road network |
| **Filter File** | `.txt` file defining positive and negative ATKIS function-code filters |

A ready-to-use sample dataset satisfying all five requirements is provided in
the `Testdaten/` folder at the project root — see
[quickstart.md → Sample Data](quickstart.md#sample-data). Its CRS is
**ETRS89 / UTM zone 33N (EPSG:25833)**, which matches the plugin's default CRS.

---

## UI Language

This document refers to input fields by their English source label and stable abbreviation
(HU, RN, Part, Aux). The plugin's source language is English; QGIS automatically loads a German
translation (`i18n/IBTool_de.qm`) when the user's QGIS locale is set to German — this is controlled
by QGIS's own locale setting, not a plugin option. The abbreviations stay unchanged in both
languages, so they are the most reliable way to match a field mentioned here to the dialog.

| Doc reference | English UI label | German UI label (locale=`de`) |
|----------------|-------------------|--------------------------------|
| HU | Building Footprints * | Gebäudegrundrisse * |
| RN | Road Network * | Straßennetz * |
| Part | Partitions * | Partitionen * |
| Aux | Auxiliary Data | Hilfsdaten |
| Filter File | Filter TXT (optional) | Filter TXT (optional) |
| Output file | Output File * | Ausgabedatei * |
| Working directory | Workspace * | Arbeitsverzeichnis * |
| CRS field | Spatial Reference | Koordinatenreferenzsystem |

If this table ever falls out of sync with the plugin, `i18n/IBTool_de.ts` is the authoritative
source for all translated strings.

---

## General Rules

- All layers must use the same **Coordinate Reference System (CRS)**. The CRS is set in the plugin interface (default: `EPSG:25833`).
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
| Minimum features | 1 |
| Required field | `NAME` — partition label (e.g. `PART_123`) |
| Name format | `PART_<number>` (e.g. `PART_36`, `PART_433`) |
| Part:HU ratio | Should not exceed 1:10,000. Too few partitions leads to very long per-partition runtimes. |

The partitioning defines independent processing units. In the plugin interface a subset can be specified by partition name list or start/end range.

If you have no partitioning layer, the companion plugin **[IB-Tool (Partitioning)](https://github.com/IB-Tool/ibtoolpartion)** derives one from building footprints and writes exactly the `PART_<number>` format described above.

### Aux — Auxiliary Layer

| Property | Requirement |
|----------|-------------|
| Geometry type | **LineString** |
| Minimum features | 10 |

The Aux layer is merged with RN and used to refine block derivation (e.g. additional barriers or boundaries). Polygon layers are not supported here.

### Filter File

| Property | Requirement |
|----------|-------------|
| File format | Plain text (`.txt`) |
| Encoding | UTF-8 |
| Required sections | `#Filter positive` and `#Filter negative` (in that order) |

Controls which buildings are included or excluded. Format:

```text
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
- Only the **first 10 characters** of each entry are matched against the `fkt`/`gfkzshh`/`funktion` field.
- **Positive filter**: only buildings whose code matches an entry are retained.
- **Negative filter**: buildings whose code matches an entry are excluded.

### Output and Working Paths

| Property | Requirement |
|----------|-------------|
| Output file | Full path to an **empty GeoPackage (`.gpkg`) that must be created before starting the run**, with an individual, descriptive name (e.g. `result_2026-07-01.gpkg`). Its contents are overwritten by the processing result. See [quickstart.md → Creating the output file](quickstart.md#creating-the-output-file). |
| Working directory | Path for intermediate files. The directory is created automatically during processing if needed. |

---

## Validation Checks

The **Check** button in the dialog runs all checks before processing. Critical errors block the **Start** button; warnings are informational.

| Check | Type | Description |
|-------|------|-------------|
| File paths | Error | Input-layer and filter-file paths must be specified and exist |
| Layer loadability | Error | Files must be loadable as valid QGIS layers |
| Empty layers | Error | Layers must not be empty (0 features) |
| Minimum features HU | Error | At least 50 features required |
| Minimum features RN | Error | At least 30 features required |
| Minimum features Part | Error | At least 1 feature required |
| Minimum features Aux | Error | At least 10 features required |
| CRS match | Error | All layers must use the CRS selected in the UI |
| HU geometry type | Error | Must be polygon geometry |
| HU required field | Error | Field `fkt`, `gfkzshh`, or `funktion` must be present |
| RN geometry type | Error | Must be line geometry |
| Part geometry type | Error | Must be polygon geometry |
| Aux geometry type | Error | Must be line geometry |
| Multipart geometries | Error | Line layers must not contain MultiLineString features with more than one part |
| Part required field | Error | Field `NAME` must be present |
| Part name format | Error | NAME values must match the `PART_<number>` pattern |
| Part:HU ratio | Warning | Ratio of HU to Part should not exceed 1:10,000 |
| Filter file format | Error | Sections `#Filter positive` and `#Filter negative` required |
| Output paths | Error | Output path must include a directory and end with `.gpkg`; workspace path must be specified |

---

## Related Files

| File | Content |
|------|---------|
| [`docs/how-it-works.md`](how-it-works.md) | Full algorithmic pipeline — how input layers are used in each step |
| [`docs/parameterization.md`](parameterization.md) | Processing parameters, defaults, and sensitivity notes |
| [`docs/data-preparation.md`](data-preparation.md) | Tutorial: producing HU/RN/Aux from ATKIS raw data |
| [`docs/data-sources.md`](data-sources.md) | Per-state ATKIS portal, format, and dataset reference |
| [`helpers/check.py`](../helpers/check.py) | `InputValidator` class implementing all validation checks |
