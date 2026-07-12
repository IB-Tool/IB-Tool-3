# CONFIG.ini — Configuration File Reference

## Overview

IBTool supports an optional `CONFIG.ini` file that pre-fills all dialog fields on
plugin start. Place the file in the plugin root directory; if it exists and
`auto_load_last_used = True`, every field (input paths, processing parameters, CRS,
log settings) is populated automatically before the dialog opens. The current dialog
state can be written back to `CONFIG.ini` at any time via the **Config speichern**
button.

---

## File Location

```
<QGIS profile>/python/plugins/<plugin-folder>/CONFIG.ini
```

The plugin root is the directory that also contains `helpers/`, `ibtool_tools/`, and
`ibtool/`. The filename must be exactly `CONFIG.ini` (case-sensitive on Linux/macOS).

A commented template is provided at `docs/CONFIG.ini.example`.

---

## Configuration Sections

### `[INPUT_DATA]`

Paths to the five input datasets. Leave a key empty or omit it to skip that field.

```ini
[INPUT_DATA]
building_footprints_path = C:/data/buildings.shp
road_network_path        = C:/data/streets.shp
partitions_path          = C:/data/partitions.shp
aux_layer_path           = C:/data/auxiliary.shp
filter_file_path         = C:/data/filter.txt
```

When `filter_file_path` is set, the filter file is parsed automatically and the
positive/negative filter lists in the **Filtering** tab are populated.

---

### `[PROCESSING]`

All numeric processing parameters. Values of `0` are treated as "not set" and leave
the corresponding dialog field unchanged.

```ini
[PROCESSING]
# MST / spatial analysis
road_length_threshold  = 50.0      # Dead-end street threshold (meters)
coordinate_tolerance   = 0.0001    # Coordinate comparison tolerance
buffer_distance        = 5.0       # Intersection buffer distance (meters)

# Footprint density analysis
grid_size              = 100.0     # Grid cell size for density analysis (meters)
min_building_count     = 5         # Minimum buildings per grid cell
density_threshold      = 0.3       # Density threshold (0.0–1.0)

# Clustering
min_cluster_size       = 3         # Minimum buildings per cluster
max_distance           = 200.0     # Maximum distance between cluster members (meters)

# Coordinate system and output
crs_epsg               = 25833     # EPSG code → written as EPSG:25833 into dialog
output_format          = gpkg      # Persisted in config; current UI workflow writes GeoPackage output

# Settlement analysis parameters (UI tab: Parameters)
min_overlap_blocks      = 0.0      # Minimum building coverage per block (%)
global_footprint_density = 0.0     # Global footprint density threshold (0 = auto)
min_area               = 0.0       # Minimum building footprint area (m²)
min_patch_size         = 0.0       # Minimum settlement patch size (m²)
max_hole_size          = 0.0       # Maximum hole size to close (m²)
max_gap_size           = 0.0       # Maximum gap size to close (m²)

# Partition selection
part_start             = -1        # First partition index (-1 = all)
part_end               = -1        # Last partition index (-1 = all)
part_list              = #         # Comma-separated list of partition IDs (# = all)
```

---

### `[OUTPUT]`

```ini
[OUTPUT]
workspace_directory  = C:/projects/my_project     # Workspace folder
output_directory     = C:/projects/my_project/results/ibtool_result.gpkg  # Historical key name: full output file path for OutputPath
output_prefix        = ibtool_result              # Stored in config, currently not applied by the runtime workflow
auto_save            = True
add_to_map           = True
overwrite_existing   = False
```

`workspace_directory` fills the `WorkspacePath` field. Despite its historical name,
`output_directory` fills the `OutputPath` field directly and therefore must contain a
full output file path, not just a directory.

---

### `[UI]`

```ini
[UI]
auto_load_last_used    = True    # Apply CONFIG.ini to dialog on every plugin start
show_progress_details  = True
log_level              = INFO    # CRITICAL | WARNING | INFO | SUCCESS
log_directory          =         # Leave empty for default (plugin root/logs/)
remember_window_size   = True
```

Set `auto_load_last_used = False` to disable automatic field population while keeping
the file for manual reference.

---

## Setup

1. Copy the template:
   ```
   docs/CONFIG.ini.example  →  CONFIG.ini   (plugin root)
   ```
2. Edit `CONFIG.ini` — uncomment keys and set paths for your project.
3. Use forward slashes or double backslashes in paths:
   - `C:/data/file.shp` ✓
   - `C:\\data\\file.shp` ✓
   - `C:\data\file.shp` ✗ (single backslash is an escape character in INI parsers)

---

## Saving Settings from the Dialog

Click **Config speichern** in the bottom button bar of the IBTool dialog. This writes
the current values of all dialog fields back to `CONFIG.ini`, creating or overwriting
the file. The following fields are saved:

| Config key | Dialog widget |
|---|---|
| `building_footprints_path` | HuPath |
| `road_network_path` | RnPath |
| `partitions_path` | PartPath |
| `aux_layer_path` | AuxPath |
| `filter_file_path` | FilterPath |
| `workspace_directory` | WorkspacePath |
| `output_directory` | OutputPath |
| `log_level` | LogLevelBox |
| `log_directory` | LogDirPath |
| `min_overlap_blocks` … `max_gap_size` | Parameter spinboxes |
| `part_start`, `part_end`, `part_list` | Partition fields (Debugging tab) |

---

## Programmatic Access

```python
# Read the loaded configuration
config = self.config_manager.get_config()
print(config.processing.road_length_threshold)

# Get all processing parameters as a flat dict (for algorithm calls)
params = self.config_manager.get_processing_parameters()

# Check whether CONFIG.ini exists
if self.config_manager.config_exists():
    missing = self.config_manager.get_missing_paths()
```

`ConfigManager` is instantiated in `IBTool.__init__` and accessible as
`self.config_manager` throughout the plugin lifecycle.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Fields not populated on start | `auto_load_last_used = False` or file not found | Check `[UI]` section; confirm file is in plugin root |
| Path not loaded | Single backslash in path | Replace `\` with `/` or `\\` |
| Save overwrites custom comments | Expected behavior — INI format does not preserve comments | Keep comments in `CONFIG.ini.example` only |
| Wrong field values after save | Dialog had stale values before clicking the button | Re-check dialog fields before saving |

---

## Related Files

| File | Content |
|---|---|
| `helpers/config_manager.py` | `ConfigManager` class — loading, saving, validation |
| `docs/CONFIG.ini.example` | Commented template for all supported keys |
| `ibtool/ibtool/ibtool.py` | `_apply_config_to_ui()`, `_save_config_from_ui()` |
