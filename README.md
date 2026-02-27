# IBTool

![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-blue)
![License](https://img.shields.io/badge/license-GPL%20v2-green)
[![codecov](https://codecov.io/gh/K3lT10N/IB-Tool-3/graph/badge.svg?token=O2KUA158A3)](https://codecov.io/gh/K3lT10N/IB-Tool-3)
![Python](https://img.shields.io/badge/Python-3.11-blue)


## Description

**IBTool** is a QGIS plugin for the automatic delineation of **Urban Growth Boundaries (UGBs)** based on building footprints and topographic data. It implements the method described in:

> Harig, O.; Hecht, R.; Burghardt, D.; Meinel, G. **Automatic Delineation of Urban Growth Boundaries Based on Topographic Data Using Germany as a Case Study.** *ISPRS Int. J. Geo-Inf.* **2021**, *10*(5), 353. https://doi.org/10.3390/ijgi10050353

The plugin delineates settlement boundaries at a fine-grained level — the boundary follows individual buildings rather than administrative units. It processes large datasets partition by partition and produces GeoPackage output ready for use in spatial analysis and planning.

---

## Features

- **Semantic and spatial building filtering:**
  - Three-stage filter: negative function-code filter → spatial density filter → minimum size filter.
  - Configurable positive/negative filter lists based on ATKIS building function codes (BauGB § 35).

- **Block-based density analysis:**
  - Derives street blocks and city blocks from the road and auxiliary network.
  - Calculates local and global building coverage ratio (BCR) per block.
  - Classifies blocks with BCR > 18% as densely developed (directly assigned to the UGB).

- **MST-based building aggregation:**
  - Delaunay triangulation on building centroids, edge-weighted by building-edge distance.
  - Minimum Spanning Tree (Kruskal algorithm via networkx); road-crossing edges removed.
  - Iterative grouping into oriented Minimum Bounding Rectangles (MBRs) with BCR validation.

- **Boundary refinement:**
  - EdgeCatch: snaps MBR boundaries to the nearest road segments.
  - GapClose: closes holes (> 1 ha removed) and bridges narrow gaps (≤ 70 m) via double-buffer.
  - PatchRemove: removes splinter areas (< 1 ha, < 20 buildings).

- **QGIS integration:**
  - Processes `.shp` and `.gpkg` inputs; writes results as GeoPackages.
  - Built-in input validation with Check button; progress bar; configurable log levels.

---

## Requirements

- **QGIS**: Version 3.40–3.50
- **Python**: Version >= 3.11

- Required Python libraries:
  - `numpy`
  - `pytest`
  - `scipy`
  - `sklearn`
  - `networkx`
  - `PyQt5`
  - `qgis.core`

---

## Installation

### Option 1 — Install from ZIP (recommended)

The easiest way to install IBTool is to download the ready-to-use ZIP file from the [GitHub Releases](https://github.com/K3lT10N/IB-Tool-3/releases) page and install it directly inside QGIS:

1. Go to the [Releases](https://github.com/K3lT10N/IB-Tool-3/releases) page and download the latest `ibtool_<version>.zip`.
2. Open QGIS.
3. In the menu bar, click **Plugins → Manage and Install Plugins…**
4. Switch to the **Install from ZIP** tab.
5. Click the **…** button, select the downloaded ZIP file, then click **Install Plugin**.
6. The plugin is now available under **Plugins → IB-Tool**.

> The ZIP file is a self-contained plugin package and does not require any manual path configuration.

---

### Option 2 — Manual installation (not recommended)

> **Note:** The repository contains many files that are not needed at runtime — documentation, tests, CI configuration, etc. Installing from the repository ZIP will copy all of these into your plugins folder. Use Option 1 (install from ZIP release) for a clean, production-ready install.

1. **Download** the repository as a ZIP or clone it:
   ```bash
   git clone https://github.com/K3lT10N/IB-Tool-3.git
   ```
2. **Copy to the QGIS plugins folder:**
   - Windows: `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
   - Note: The AppData folder may be hidden — enable "Show hidden items" in the Explorer settings.
3. **Configure the QGIS path (optional):**
   - IBTool detects QGIS automatically via the `QGIS_PREFIX_PATH` environment variable or common install locations.
   - If QGIS is installed in a non-standard location, set `QGIS_PREFIX_PATH` manually, e.g.:
     ```bash
     export QGIS_PREFIX_PATH=/opt/qgis
     ```
4. **Activate the plugin:**
   - Start QGIS and enable IBTool in **Plugins → Manage and Install Plugins**.

---

## Usage

1. Launch the plugin from the QGIS menu bar under **Plugins → IB-Tool**.
2. Load your geodata (e.g. building footprints, road networks) directly through the tool's interface.
3. Set a workspace folder — this is used to store intermediate and final results.
4. Configure the parameter settings in the dialog window.
5. Click the **Check** button to validate all input data before processing. Fix any reported errors before continuing.
6. Start processing:
   - Monitor progress in the progress bar.
   - Results are saved as `.gpkg` files.

---

## Input Data

The plugin works with several input files:

- **HU (Building Footprints)**: Building outlines.
- **RN (Road Network)**: Road network.
- **Part (Partitioning)**: Zoning to restrict the analysis area.
- **Aux (Auxiliary Layers)**: Helper layers for refining analyses.
- **Filter File**: A `.txt` file defining positive and negative filters.

### Input Data Requirements

#### General Rules

- All layers must use the same **Coordinate Reference System (CRS)**. The CRS is set in the plugin interface (e.g. `EPSG:25832`).
- All layers must be loadable as valid QGIS vector layers (Shapefile `.shp` or GeoPackage `.gpkg`).
- No layer may be empty (0 features).
- Line layers (RN, Aux) should not contain **multipart geometries**. If present, these should be dissolved before processing (`native:multiparttosingleparts`).

#### HU — Building Footprints

| Property | Requirement |
|----------|-------------|
| Geometry type | **Polygon** (no points or lines) |
| Minimum features | 50 |
| Required field | `fkt` or `funktion` — contains the building function code per the ATKIS object type catalogue (e.g. `31001_1000` for residential buildings). Used for filtering. |

The `fkt` / `funktion` field is matched against the filter file. Only the first 10 characters of the function code are used for comparison.

#### RN — Road Network

| Property | Requirement |
|----------|-------------|
| Geometry type | **LineString** (no polygons or points) |
| Minimum features | 30 |
| Multipart | Not recommended — use single-part geometries |

The `length` field is calculated automatically during processing and does not need to be present. Road segments shorter than 50 m (dead ends) are automatically filtered during MST calculation.

#### Part — Partitioning

| Property | Requirement |
|----------|-------------|
| Geometry type | **Polygon** |
| Required field | `NAME` — partition label, e.g. `PART_123` |
| Name format | Values in the `NAME` field should follow the pattern `PART_<number>` (e.g. `PART_36`, `PART_433`) |
| Part:HU ratio | The ratio of Part features to HU features should not exceed 1:10,000. Too few partitions will result in very long processing times per partition. |

The partitioning defines the analysis areas. Per partition, buildings and roads are selected and processed separately. In the plugin interface a list of partition names or a range (start/end) can be specified.

#### Aux — Auxiliary Layers

| Property | Requirement |
|----------|-------------|
| Geometry type | Polygon or LineString |
| Minimum features | 10 |

The Aux layer is merged with the RN layer and used to refine the analysis (e.g. additional barriers or boundaries).

#### Filter File

| Property | Requirement |
|----------|-------------|
| File format | Text file (`.txt`) |
| Encoding | UTF-8 |
| Required sections | `#Filter positive` and `#Filter negative` |

The filter file controls which buildings are included or excluded from the analysis. Structure:

```
#Filter positive
31001_1000, Wohngeb
31001_1010, Wohnhaus
31001_1100, GemischtesWohnen
31001_1120, WohnenHandelDienst
31001_1121, WohnVerw
31001_1122, WohnBuero
...

#Filter negative
31001_1310, Freizeit
31001_2600, Entsorgung
31001_2720, GebLandForst
31001_2721, Scheune
31001_2723, Schuppen
31001_2724, Stall
...

```

- Lines starting with `#` are section headers or comments.
- Empty lines are ignored.
- Only the **first 10 characters** of each line are used for matching against the `fkt`/`funktion` field.
- **Positive filter**: Only buildings whose function code matches one of these entries are included.
- **Negative filter**: Buildings whose function code matches one of these entries are excluded.

#### Output and Working Paths

| Property | Requirement |
|----------|-------------|
| Output file | Path for the result file (`.gpkg`). The parent directory must exist. |
| Working directory | Path for intermediate results. Created during processing — the parent directory must exist. |

### Input Data Validation

The plugin includes built-in validation for all input data. The **Check** button in the dialog validates the data before processing. The following checks are performed:

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
| HU required field | Error | Field `fkt` or `funktion` must be present |
| RN geometry type | Error | Must be line geometry |
| Multipart geometries | Warning | Line layers should not contain multipart geometries |
| Part required field | Error | Field `NAME` must be present |
| Part name format | Warning | NAME values should match the `PART_` pattern |
| Part:HU ratio | Warning | Ratio of Part to HU should not exceed 1:10,000 |
| Filter file format | Error | Sections `#Filter positive` and `#Filter negative` required |
| Output paths | Error | Output and working directories must exist |

Critical errors disable the **Start** button until resolved. Warnings are shown but do not block processing. Validation also runs automatically when processing starts.

---

## How It Works

The plugin processes each partition through a fixed sequence of steps:

1. **Blocker** — derives street and city blocks from the road + auxiliary network
2. **ImportFilter** — 3-stage semantic/spatial/size filter removes non-UGB buildings
3. **FootprintDensity** — calculates building coverage ratio (BCR); classifies dense blocks (BCR > 18%)
4. **CreateMST** — Delaunay triangulation → MST (Kruskal); removes road-crossing edges
5. **MST_Clustering** — groups buildings into oriented MBRs, validated by local BCR threshold
6. **AddSingleBuilding** — adds bounding rectangles for large isolated buildings (> 300 m²)
7. **EdgeCatch** — snaps boundaries to road network (nearest road within 25 m)
8. **GapClose** — closes holes > 1 ha; bridges gaps ≤ 70 m (4,900 m²) via double-buffer
9. **PatchRemove** — removes splinter areas (< 1 ha and < 20 buildings)

For the full algorithmic description including pseudocode, parameter references, and accuracy results, see **[docs/how-it-works.md](docs/how-it-works.md)**.

---

## Contributing & Development

The project uses GitHub Actions and Docker for CI, and pytest for the test suite.

For the full development setup, CI/CD pipeline details, Docker environment, test structure, and code quality tooling, see **[docs/contributing.md](docs/contributing.md)**.

---

## Logging System

IBTool includes a comprehensive logging system that outputs messages to three locations:

1. The user interface (message window)
2. A log file in the configurable log directory
3. The QGIS message log

### Log Levels

The system supports four log levels in descending priority:

- **CRITICAL**: Critical errors that affect execution
- **WARNING**: Warnings indicating possible issues
- **INFO**: Informational messages about normal operation
- **SUCCESS**: Detailed success and debug messages

Selecting a log level shows all messages at that level and higher priority. Example: selecting "INFO" shows INFO, WARNING, and CRITICAL messages, but not SUCCESS messages.

### Configuration

The log level can be set in the user interface:

1. Select the desired level of detail from the "Log Level" dropdown.
2. Optionally: choose a different directory for log files via the "Log Directory" button.

### Log Files

Log files are stored by default in the `logs` subdirectory of the plugin and are named with a timestamp in the format `logfile_YYYY-MM-DD_HH-MM-SS.txt`. A new log file is created each time the plugin starts.

---

## License

This plugin is licensed under the **GNU General Public License v2.0**. You are free to use, modify, and redistribute it as long as the conditions of the GPL are met.

---

## Author

- **Author**: Oliver Harig — Leibniz Institute of Ecological Urban and Regional Development (IOER), Dresden
- **Created with support from**: [QGIS Plugin Builder](http://g-sherman.github.io/Qgis-Plugin-Builder/)

### Publication

If you use IBTool in research, please cite:

> Harig, O.; Hecht, R.; Burghardt, D.; Meinel, G. Automatic Delineation of Urban Growth Boundaries Based on Topographic Data Using Germany as a Case Study. *ISPRS Int. J. Geo-Inf.* **2021**, *10*(5), 353. https://doi.org/10.3390/ijgi10050353

---

## Troubleshooting

- Use the **Check** button to validate input data before processing. Error messages contain specific hints for fixing issues.
- Make sure all input data uses the same **CRS** (coordinate reference system).
- Verify that all dependencies (e.g. libraries) are correctly installed.
- Consult the log messages in the plugin's message window to identify errors.
