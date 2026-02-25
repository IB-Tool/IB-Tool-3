# Changelog

All notable changes to IBTool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2026-02-25

### Added
- **EdgeCatch**: New preprocessing step `_filter_roads_near_buildings()` that splits the road network into 10 m segments, stamps a stable `seg_id` field onto each segment, buffers each segment by 25 m, and retains only segments whose buffer intersects a building footprint; matching is done via `seg_id` attribute (not FID or spatial overlap) so neighbouring segments outside a qualifying buffer are never accidentally included.
- **EdgeCatch**: Extracted per-feature loop body into `process_single_feature()`; moved all private helpers and algorithm constants to `helpers/edge_catch_utils.py` per project convention; added `debug_mode` parameter to `edge_catch`, `filter_roads_near_buildings`, and `process_single_feature`; added `save_debug_layer` checkpoints at `road_segs_near_buildings`, `roads_selection`, `ortho_lines`, `polygons_in_block`, `result_polygons`, and `polygons_merged`; switched all `processing.run` calls in helpers to `safe_processing_run`; removed unused imports, dead inner functions, and dead constants; translated German docstring and comments to English; fixed `polygones_merge` typo to `polygons_merge`.

### Changed
- **EdgeCatch**: Per-feature `save_debug_layer` calls inside `process_single_feature()` removed — only two global checkpoints remain (`road_segs_near_buildings`, `polygons_merged`) to prevent hundreds of files being written per run; `DEBUG_TOOL_NAME` renamed to `"03_EdgeCatch"` to match the numbered pipeline-order convention.
- **GapClose**: `_DEBUG_TOOL_NAME` renamed from `"03_GapClose"` to `"04_GapClose"` to maintain correct call-order numbering after EdgeCatch was inserted at position 03.
- **ConfigManager**: Added `debug_mode` and `delete_part_log` boolean fields to `ProcessingConfig` with full read/write support in `load_config()` and `save_config()`; `_save_config_from_ui()` now also persists `SpatialReferenceBox` (as `crs_epsg`), `DebugModeBox`, and `PartLogBox`; `_apply_config_to_ui()` now restores both checkbox states on dialog open.

### Fixed
- **EdgeCatch**: `debug_mode` was not forwarded to the `edge_catch()` call in `ibtool.py`, causing all debug checkpoints to be silently skipped; fixed by passing `debug_mode=debug_mode` to the call.
- **InputValidator**: `fkt` field values were read by numeric index (`feature[fkt_idx]`) which could resolve to a wrong field when provider and `QgsFields` orderings diverge; switched to name-based access (`feature[fkt_field]`). Buildings with `fkt = "0"` (no function code assigned) are now silently skipped instead of being flagged as ATKIS-format violations.

---

## 2026-02-24

### Added
- **safe_processing.py**: New shared helper module in `helpers/` that centralises `safe_processing_run()`, eliminating the duplicate definitions that previously existed in both `GapClose.py` and `GapFix.py`.

### Changed
- **GapClose**: Refactored into focused private helpers (`_dissolve_union`, `_gap_select`, `_close_block_gaps`, `_close_buffer_gaps`) so `gap_close()` is a short orchestrator; replaced all magic numbers with named module-level constants (`TOPOLOGY_SNAP_BUFFER_M`, `BOUNDARY_OVERLAP_THRESHOLD_PCT`, etc.).
- **GapFix**: Removed local `safe_processing_run()` duplicate and switched to the shared `helpers/safe_processing` import.
- **AddSingleBuilding**: Refactored — translated German inline comments to English, replaced magic numbers with named module-level constants (`_PREDICATE_DISJOINT`, `_PREDICATE_INTERSECTS`, `_OPERATOR_GREATER_THAN`, `DEFAULT_AREA_THRESHOLD`, etc.), converted docstring from Sphinx to Google style, and made `workspace_path` an optional keyword argument (`=None`) to align the signature with existing tests.
- **Blocker**: Refactored `blocker()` into three focused private helpers (`_build_block_polygons`, `_remove_blocks_without_buildings`, `_assign_block_names`) so the public function is a short orchestrator; replaced the `'TEMPORARY_OUTPUT'` string literal with `QgsProcessing.TEMPORARY_OUTPUT`, named magic predicate/method codes as module constants, translated the German parameter name `strassen` → `road_network`, and converted the docstring to Google style. Added `debug_mode` / `workspace_path` parameters and `save_debug_layer` checkpoints at `roads_in_partition`, `blocks_raw`, and `blocks_with_buildings`; switched all `processing.run` calls to `safe_processing_run`.
- **AddSingleBuilding**: Added `debug_mode` / `workspace_path` parameters and `save_debug_layer` checkpoints at `centroids_outside_cluster`, `buildings_outside_cluster`, `buildings_large`, and `bounding_rects`; switched all `processing.run` calls to `safe_processing_run`.
- **Blocker, AddSingleBuilding, GapClose**: Debug output folders are now numbered by pipeline call order via `_DEBUG_TOOL_NAME` constants (`01_Blocker`, `02_AddSingleBuilding`, `03_GapClose`), so folders sort chronologically in the file system.

---

## 2026-02-23

### Added
- **GapClose**: Added `Logger.log` output for feature counts of `holes_closed`, `gap_poly_max_size`, and `final_gap2` (individually and as a combined summary) directly before the final merge, so filter results are always visible in the plugin log without requiring debug mode.
- **GapClose**: Added missing `save_debug_layer` checkpoint for `holes_closed` (`07b_holes_closed`) after `native:deleteholes` in the main pipeline.

### Changed
- **GapFix**: Replaced the polygonize-based gap-fill algorithm with a buffer ring + pairwise spatial intersection approach: `fixgeometries` → hole closing (polygonize → collect → buffer(0, dissolve=True)) → singleparts with `gap_uid` → per-polygon buffer rings → pairwise ring intersection → validate (gap must intersect both source polygons) → merge into the neighbor with the longest shared boundary.
- **GapClose**: Default `gap_dist` reduced from 30 m to 15 m to match empirical test results and the `gap_close_in_holes` default.
- **GapClose**: `gap_select()` now logs per-call statistics (input gap count, overlapping segments, ratio-passed, matched FIDs) so filter behaviour is traceable without debug mode.
- **system_utils**: `manage_directory()` now also deletes the `debug` folder when `del_part_log=True`, preventing stale debug files from accumulating between runs.

### Fixed
- **IBTool**: Final output was written from `merge` (the pre-GapFix layer) instead of `gap_fixed`, silently discarding all GapFix results; fixed by passing `gap_fixed` to `save_temp_layer_to_gpkg`.

---

## 2026-02-22

### Added
- **debug_utils**: Added `_next_debug_index()` helper that counts existing `.gpkg` files in the tool's debug folder to assign sequential step numbers, enabling chronological sorting in a GIS.
- **GapFix**: Added `safe_processing_run()` module-level wrapper (mirroring `GapClose`) so all four QGIS algorithm calls are covered by debug-snapshot and geometry-repair error handling.
- **GapClose**: Added `gap_close_in_holes()` function that closes gaps within holes via morphological closing (positive buffer → negative buffer, default 15 m), then removes any remaining holes smaller than `max_hole_size`.

### Changed
- **GapFix**: All four bare `processing.run()` calls replaced with `safe_processing_run()` via `_dbg` dict; the `except` block now saves the input layer as an `_err` debug snapshot when `debug_mode` is active.
- **debug_utils**: `save_debug_layer()` and `save_debug_features()` now prefix filenames with a zero-padded 3-digit index (`NNN_`) and accept an `is_error` parameter; error snapshots additionally receive the `_err` suffix to distinguish failed processing steps from intentional checkpoints.
- **GapClose**: `safe_processing_run()` now passes `is_error=True` to `save_debug_layer()` and omits the manual `_error` suffix from the step name, relying on the `is_error` convention instead.
- **debug-mode.md**: Fully revised to document the numbered file naming convention, checkpoint vs. error distinction, and the `is_error` parameter on both debug functions.
- **error-handling.md**: Updated output-path description to reflect the new `NNN_` prefix and `_err` suffix convention.

### Fixed
- **IBTool**: `debug_mode` was never forwarded to `gap_fix()` in `ibtool.py`, so no debug files were ever created despite the checkbox being active; fixed by passing `debug_mode=debug_mode` at the call site.
- **GapFix**: No intermediate results were saved during a successful run; added numbered `save_debug_layer` checkpoints after each pipeline step (`fixed`, `densified`, `lines`, `faces`, `gap_fix_result`) so the full processing sequence can be traced visually in a GIS.

---

## 2026-02-21

### Changed
- **GapFix**: Replaced the broken ArcPy-style buffer/diff approach with a topological rebuild via polygonize — pipeline is now fixgeometries → densify → polygonstolines → polygonize → classify empty faces → merge narrow gaps (< `max_gap`, default 10 m) into the neighbor with the longest shared boundary; interior rings (holes) are preserved by skipping faces that touch only one input polygon. Added `max_gap` and `debug_mode` parameters; `InputRoadnetwork` and `bufferwidth` are retained for API compatibility but no longer used.

---

## 2026-02-20

### Added
- **ConfigManager**: Integrated the existing (previously unused) `ConfigManager` into `IBTool.__init__` so `CONFIG.ini` is loaded automatically on plugin startup and all UI fields (paths, CRS, log level, partition params, settlement analysis parameters) are pre-filled.
- **IBTool**: Added `_apply_config_to_ui()` method that reads `CONFIG.ini` and populates all dialog fields when `auto_load_last_used = True`.
- **IBTool**: Added `_save_config_from_ui()` method that writes the current UI state back to `CONFIG.ini`.
- **ibtool_dialog_base.ui**: Added `SaveConfigButton` ("Config speichern") to the bottom button bar for saving current UI settings to `CONFIG.ini`.
- **ProcessingConfig**: Extended with six missing settlement-analysis fields (`min_overlap_blocks`, `global_footprint_density`, `min_area`, `min_patch_size`, `max_hole_size`, `max_gap_size`) so the full parameter set is covered by the config schema.
- **docs/CONFIG.ini.example**: Documented the six new settlement-analysis parameters in the `[PROCESSING]` section.
- **docs/CONFIG_README.md**: Rewrote configuration reference in English; corrected outdated API method names; added full parameter tables including the six new settlement-analysis fields and the save-button workflow.

### Changed
- **AddSingleBuilding**: Merge with `rect_merge` removed from `add_single_bdg` and delegated to the caller; the function now returns only the bounding rectangles for standalone buildings outside existing cluster polygons.

### Fixed
- **AddSingleBuilding**: `minimumboundinggeometry` incorrectly collapsed all buildings into a single bounding box because the grouping field `'node'` was not unique per feature — fixed by inserting an auto-incremental ID field before the operation.
- **AddSingleBuilding**: Replaced `native:centroids` with `native:pointonsurface` to guarantee an interior point for irregular polygon geometries.

---

## 2026-02-19

### Added
- **ibtool_dialog_base.ui**: Added `DebugModeBox` checkbox ("Fehlerhafte Features speichern") to the debug tab for enabling debug mode from the UI.

### Fixed
- **CI**: Codecov received no coverage report because container-internal paths (`/plugins/ibtool/…`) were not stripped before upload — added `sed` step to normalize paths to repo-relative form.
- **CI**: Branch trigger was set to `main` instead of `master`, so pushes to the main branch never triggered the pipeline.
- **pytest.ini**: Section header `[tool:pytest]` was invalid for `pytest.ini` (only valid in `setup.cfg`) — corrected to `[pytest]`; `--cov` flags removed from `addopts` to avoid failures in environments without `pytest-cov`.
- **.coveragerc**: `source` pointed to non-existent `ibtool/ibtool` subdirectory — corrected to `ibtool` (full package).

### Removed
- **Tests**: Deleted `test_mst_components.py`, `test_mst_performance_edge_cases.py`, and `test_mst_modules.py` — all tests were file-level skipped and referenced a modular MST architecture (`ibtool_tools/mst/`) that does not yet exist.
- **Tests**: Deleted `qgis_interface.py` test helper — used deprecated QGIS 2.x API (`QgsMapLayerRegistry`) incompatible with QGIS 3.x.
- **test_create_mst**: Removed 6 skipped test methods whose skip reason was `"MST core functionality not working — returns None"`.

---

## 2026-02-17

### Fixed
- **GapClose produces empty output**: `native:dissolve` silently fails on large MultiPolygon sets (7801+ features), producing null geometry (`isEmpty=True, isNull=True, wkbType=Unknown`). Replaced with `native:collect` → `native:buffer(distance=0, dissolve=True)` workaround which forces a reliable GEOS union.

---

## 2025-02-07

### Added
- Input data validation system (`helpers/check.py`) with `InputValidator` class and `ValidationResult` dataclass
- **Check button** in plugin dialog for pre-processing validation of all input data
- Comprehensive validation checks: file existence, layer validity, CRS match, geometry types, required fields, filter file format, output paths, minimum feature counts (HU>=50, RN>=30, Aux>=10), multipart geometry detection, Part-to-HU ratio check
- Clear success message ("Validierung erfolgreich") when all checks pass
- Actionable error messages with hints for fixing issues (in German)
- Start button is disabled when validation errors are found and re-enabled when input paths change

### Changed
- Replaced `check_projection()` call in `start_processing()` with comprehensive `InputValidator.validate_all()` gate
- Processing now aborts with clear error messages if validation fails
- Updated README.md with detailed input data requirements and validation documentation

---

## 2025-01-19

### Added
- Global QGIS defaults configuration (`helpers/qgis_defaults.py`) for consistent tool behavior
- Modular MST architecture with specialized processors (DelaunayProcessor, StreetProcessor, MSTCalculator)
- Comprehensive developer guidelines and architecture preferences in CLAUDE.md
- Comprehensive import structure documentation (`IMPORT_CLEANUP_SUMMARY.md`)
- GapFix module for closing gaps between partition boundaries using QGIS processing tools

### Changed
- **BREAKING**: Refactored CreateMST from monolithic 500-line function to modular class-based architecture
- Simplified MST configuration: removed over-engineered config system in favor of local class constants
- MST processors now use simple constructors without config parameters
- Moved business logic parameters to their respective classes (StreetProcessor.ROAD_LENGTH_THRESHOLD, MSTCalculator.COORDINATE_TOLERANCE)
- Unified Logger usage pattern across all modules (removed `Logger = Logger()` class override pattern)
- Renamed `gapfix` to `gap_fix` for naming consistency across imports and `__all__` exports
- Simplified file handling and layer export logic in main plugin workflow
- Reduced excessive logging across multiple modules (CreateMST, MST processors, edge_catch_utils) for better performance and readability

### Removed
- Obsolete nested directory structure (`ibtool/helpers/`, `ibtool/ibtool_tools/`) - 19 files
- Duplicate root-level `ibtool.py` (935 lines, superseded by `ibtool/ibtool/ibtool.py`)
- `old_helpers/` directory containing outdated file versions from August-October
- Unused gapfix imports and calls from main plugin workflow
- Total cleanup: ~4700 lines of obsolete/duplicate code

### Fixed
- Logger instantiation pattern: removed `Logger = Logger()` that was overriding the Logger class with an instance
- Circular import structure: removed unused `save_temp_layer_to_gpkg` import from geometry_utils
- Import structure clarity: documented that ROOT-level `helpers/` and `ibtool_tools/` are active (not nested versions)
- Method naming consistency: `gapfix` → `gap_fix` throughout codebase
- Error logging levels in GapClose.py (ERROR → CRITICAL for exceptions)

## [Previous Versions]

*Historical changelog entries to be added based on git history and release notes*

---

### Changelog Categories

- **Added** for new features
- **Changed** for changes in existing functionality  
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes