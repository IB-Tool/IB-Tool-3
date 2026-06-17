# IBTool 3

[![CI](https://github.com/K3lT10N/IB-Tool-3/actions/workflows/ci.yml/badge.svg)](https://github.com/K3lT10N/IB-Tool-3/actions/workflows/ci.yml)
[![QGIS Plugin CI](https://github.com/K3lT10N/IB-Tool-3/actions/workflows/qgis-plugin-ci.yml/badge.svg)](https://github.com/K3lT10N/IB-Tool-3/actions/workflows/qgis-plugin-ci.yml)
<a href="https://codecov.io/gh/IB-Tool/IB-Tool-3" > 
 <img src="https://codecov.io/gh/IB-Tool/IB-Tool-3/graph/badge.svg?token=XGTC33WCFB"/> 
 </a>
[![License: GPL-2.0-or-later](https://img.shields.io/badge/License-GPL--2.0--or--later-blue.svg)](LICENSE)
![QGIS](https://img.shields.io/badge/QGIS-3.40%2B-green)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)


## Description

**IBTool** is a QGIS plugin for the automatic delineation of **Urban Growth Boundaries (UGBs)** based on building footprints and topographic data. It is mostly based on the method described in:

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

- **Guided 4-step workflow:**
  - Step 1 *Input* — path fields with real-time existence validation.
  - Step 2 *Parameters* — numerical processing parameters with inline descriptions.
  - Step 3 *Validation* — checklist view of all pre-processing checks (errors / warnings).
  - Step 4 *Processing* — phase progress label, progress bar, live log, and result action buttons (load layer, open folder, export log) after a successful run.
  - Auto-saves UI state to `CONFIG.ini` on dialog close.

- **Debug mode:**
  - Checkbox in the dialog enables per-module GeoPackage snapshots written to `workspace/debug/<Module>/`.
  - Files are numbered sequentially (`001_after_positive_filter.gpkg`, …) and sort chronologically in any GIS.
  - All major processing modules supported: `Blocker`, `ImportFilter`, `MST_Clustering`, `AddSingleBuilding`, `EdgeCatch`, `ErodeEmptyAreas`, `GapClose`, `PatchRemove`.

- **QGIS integration:**
  - Processes `.shp` and `.gpkg` inputs; writes results as GeoPackages.
  - Built-in input validation with Check button; progress bar; configurable log levels.

---

## Requirements

- **QGIS**: Version 3.40–3.50
- **Python**: Version >= 3.11

### Runtime

| Package | Bundled with QGIS 3.40+ | Notes |
|---------|------------------------|-------|
| `numpy` | Yes | |
| `PyQt5` | Yes | |
| `scipy` | Not guaranteed | Install manually if the plugin fails to load: `pip install scipy` |
| `networkx` | Not guaranteed | Install manually if the plugin fails to load: `pip install networkx` |

If `scipy` or `networkx` are missing, QGIS will show an import error when the plugin loads. See [Troubleshooting](#troubleshooting).

### Development & Testing

To run the test suite outside of QGIS (e.g. locally or in CI):

```bash
pip install -r requirements-dev.txt
```

This installs `pytest` and `pytest-cov`. The test suite itself runs inside Docker (see `Dockerfile`) which also provides the QGIS environment including all runtime dependencies.

---

## Installation

### Option 1 — Install from ZIP (recommended)

The easiest way to install IBTool is to download the ready-to-use ZIP file from the [GitHub Releases](https://github.com/K3lT10N/IB-Tool-3/releases) page and install it directly inside QGIS:

1. Go to the [Releases](https://github.com/K3lT10N/IB-Tool-3/releases) page and download the latest `IB-Tool-3.<version>.zip`.
2. Open QGIS.
3. In the menu bar, click **Plugins → Manage and Install Plugins…**
4. Switch to the **Install from ZIP** tab.
5. Click the **…** button, select the downloaded ZIP file, then click **Install Plugin**.
6. The plugin is now available under **Plugins → IB-Tool**.

> **Important — Plugin folder name:**
> QGIS creates the plugin folder from the top-level folder inside the ZIP. The release ZIP contains the folder `IB-Tool-3`, which includes hyphens and digits. QGIS requires plugin folder names to be valid Python identifiers (no hyphens, no leading digits). If the plugin does not appear in QGIS after installation, navigate to your QGIS plugins folder (see paths below) and **rename** the extracted folder to `ibtool`:
>
> | OS | Plugins folder |
> |----|----------------|
> | Windows | `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins` |
> | Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins` |
> | macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins` |
>
> Rename: `IB-Tool-3` → `ibtool`
>
> Then restart QGIS and enable the plugin.

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
3. **Rename the plugin folder:**
   QGIS requires plugin folder names to be valid Python identifiers. The repository folder `IB-Tool-3` contains hyphens and a trailing digit, which are not allowed. **Rename** the folder to `ibtool`:
   ```
   IB-Tool-3  →  ibtool
   ```
4. **Configure the QGIS path (optional):**
   - IBTool detects QGIS automatically via the `QGIS_PREFIX_PATH` environment variable or common install locations.
   - If QGIS is installed in a non-standard location, set `QGIS_PREFIX_PATH` manually, e.g.:
     ```bash
     export QGIS_PREFIX_PATH=/opt/qgis
     ```
5. **Activate the plugin:**
   - Start QGIS and enable IBTool in **Plugins → Manage and Install Plugins**.

---

## Usage

1. Launch the plugin from the QGIS menu bar under **Plugins → IB-Tool**.
2. **Step 1 — Input:** Fill in all path fields (building footprints, road network, partitions, auxiliary layer, filter file, workspace, output). Each field shows a green ✓ or red ✗ as you type.
3. **Step 2 — Parameters:** Review and adjust the processing parameters. Refer to **[docs/parameterization.md](docs/parameterization.md)** for a full description of each parameter.
4. **Step 3 — Validation:** Click the **Check** button to run all pre-processing checks. Errors must be resolved before processing can start. Warnings are informational.
5. **Step 4 — Processing:** Click **Start**. Monitor progress via the phase label and progress bar. After a successful run, use the result action buttons to load the layer into QGIS, open the output folder, or export the log.

> **Tip:** Enable *Debug Mode* in the dialog to save intermediate GeoPackage snapshots for each processing step to `workspace/debug/`. This is useful for diagnosing unexpected results.

---

## Input Data

Five inputs are required: building footprints (HU), road network (RN), partitioning layer (Part), auxiliary layer (Aux), and a filter file. All layers must share the same CRS.

For full layer specifications, field requirements, filter file format, and the complete validation check table, see **[docs/input-data.md](docs/input-data.md)**.

---

## How It Works

The plugin processes each partition through a fixed sequence of steps:

1. **Blocker** — derives street and city blocks from the road + auxiliary network
2. **ImportFilter** — 3-stage semantic/spatial/size filter removes non-UGB buildings
3. **FootprintDensity** — calculates building coverage ratio (BCR); classifies dense blocks (BCR > threshold)
4. **CreateMST** — Delaunay triangulation → MST (Kruskal); removes road-crossing edges
5. **MST_Clustering** — groups buildings into oriented MBRs, validated by local BCR threshold
6. **AddSingleBuilding** — adds bounding rectangles for large isolated buildings (> 300 m²)
7. **EdgeCatch** — snaps boundaries to road network (nearest road within 25 m)
8. **ErodeEmptyAreas** — removes building-free voids (≥ 500 m²) enclosed within the settlement polygon
9. **GapClose** — closes enclosed holes above area threshold; bridges narrow gaps at the fringe
10. **PatchRemove** — removes splinter areas below size and building-count thresholds

For the full algorithmic description including pseudocode, parameter references, and accuracy results, see **[docs/how-it-works.md](docs/how-it-works.md)**.

---

## Contributing & Development

The project uses GitHub Actions and Docker for CI, and pytest for the test suite.

For the full development setup, CI/CD pipeline details, Docker environment, test structure, and code quality tooling, see **[docs/contributing.md](docs/contributing.md)**.

---

## Logging

IBTool writes log messages to the plugin dialog, to a timestamped log file in `logs/`, and to the QGIS message bar for critical errors. Four levels are supported: `CRITICAL`, `WARNING`, `INFO`, and `SUCCESS`. The active log level and log directory are configurable in the dialog.

For the full logging reference including level definitions, output destinations, and the debug mode, see **[docs/error-handling.md](docs/error-handling.md)**.

---

## License

This plugin is licensed under the **GNU General Public License v2.0**. You are free to use, modify, and redistribute it as long as the conditions of the GPL are met.

---

## Author

- **Author**: Oliver Harig
- **Created with support from**: [QGIS Plugin Builder](http://g-sherman.github.io/Qgis-Plugin-Builder/)
- **Development assisted by**: [Claude Code](https://claude.ai/code) (Anthropic) — AI-assisted coding, documentation, and test generation. See `ai/` and `CLAUDE.md` for the project-specific AI rules and domain knowledge used during development.

## Publication

If you use IBTool in research, please cite:

> Harig, O.; Hecht, R.; Burghardt, D.; Meinel, G. Automatic Delineation of Urban Growth Boundaries Based on Topographic Data Using Germany as a Case Study. *ISPRS Int. J. Geo-Inf.* **2021**, *10*(5), 353. https://doi.org/10.3390/ijgi10050353

> Eichhorn, S.; Harig, O.; …; Hecht, R. Assessing the suitability of settlement delineations for monitoring infilling: A web- and GIS-based expert evaluation approach. *Environ. Plan. B Urban Anal. City Sci.* **2025**, *52*(7). https://doi.org/10.1177/23998083241308407
>
> Evaluates whether automated settlement delineations — such as those generated by IBTool — are suitable for monitoring urban infill development. Using a structured web- and GIS-based expert survey, the study assesses the methodological quality and practical applicability of delineation approaches for infill analysis in urban planning contexts.

---

## Troubleshooting

- **Plugin not visible in QGIS after installation?** Check that the plugin folder is named `ibtool` (lowercase, no hyphens). ZIP installation may create a folder like `IB-Tool-3` or `IB-Tool-3.0.1.5` — rename it to `ibtool` and restart QGIS. See [Installation](#installation) for details.
- Use the **Check** button to validate input data before processing. Error messages contain specific hints for fixing issues.
- Make sure all input data uses the same **CRS** (coordinate reference system).
- If the plugin fails to load with an import error, `scipy` or `networkx` may be missing from your QGIS Python environment. Install them manually: `pip install scipy networkx`. See [Requirements → Runtime](#runtime) for details.
- Consult the log messages in the plugin's message window to identify errors.
- Enable **Debug Mode** in the dialog to write step-by-step GeoPackage snapshots to `workspace/debug/`. Load these files into QGIS and sort them by name to trace the pipeline visually. Error snapshots are marked with an `_err` suffix.
- If a partition produces unexpected output, check the debug files for the relevant module (e.g. `ImportFilter/003_after_density_buffer.gpkg` to inspect the residential zone polygon).
- See **[docs/parameterization.md](docs/parameterization.md)** for guidance on tuning the processing parameters.
