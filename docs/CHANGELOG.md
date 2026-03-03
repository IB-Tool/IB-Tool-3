# Changelog

All notable changes to IBTool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## 2026-03-03

### Added
- **Validation** (`helpers/check.py`): `gfkzshh` accepted as a third valid building-function field alongside `fkt` and `funktion`; a warning is now emitted when the positive filter produces an empty result set.
- **GapFix** (`ibtool_tools/GapFix.py`): Added support for resuming processing from an intermediate merge layer; improved per-partition log output.
- **Docs** (`docs/input-data.md`): New dedicated documentation file covering all five input layers (field requirements, geometry types, minimum feature counts), filter file format with example, output and workspace path requirements, and the complete validation check table.

### Changed
- **Validation** (`helpers/check.py`): All user-visible strings translated from German to English — layer display names (`"Gebäudeumrisse (HU)"` → `"Building footprints (HU)"` etc.), error/warning messages, hint texts, and numeric-parameter labels. NULL `fkt`/`gfkzshh`/`funktion` values now produce a **warning** instead of an error (processing can continue).
- **FootprintDensity** (`ibtool_tools/FootprintDensity.py`): Internal aggregation and join field renamed from `NAME` to `BLOCK_ID` to prevent a case-collision with the buildings layer's `name` field in QGIS expression contexts.
- **EdgeCatch** (`helpers/edge_catch_utils.py`): Added `local_visited` set to the edge-chain traversal to prevent segments from being revisited within a single chain, fixing an infinite-loop edge case on densely connected road segments.
- **README**: `## Input Data` section condensed to a four-line summary with a reference to `docs/input-data.md`; full specifications moved to the new dedicated file.

### Tests
- **`test_check.py`**: Updated layer key strings to English (`"Building footprints (HU)"` etc.); replaced German word assertions (`"leer"` → `"empty"`, `"vor"` → `"before"`); renamed `test_null_fkt_value_adds_error` → `test_null_fkt_value_adds_warning` and corrected the assertion (NULL fkt is a warning, `is_valid` remains `True`).
- **`test_footprint_density.py`**: Updated `_block_layer_with_name` factory to create a `BLOCK_ID` field instead of `NAME`; updated `_add_named_block` to set `BLOCK_ID` accordingly.

### Removed
- **`IB-Tool2.py`**: Deleted legacy root-level script.
- **`test/test_import_mst.py`**: Deleted unused test file.

---

## 2026-03-01

### Added
- **Release** (`LICENSE`): Added MIT license file.
- **Release** (`metadata.txt`): Added `license` field pointing to the MIT license.
- **Release** (`create_release_zip.py`): Added packaging script that builds a release ZIP from `metadata.txt` version, applying exclusion rules for dev-only files.
- **Linting** (`.flake8`, `.bandit`): Added Flake8 and Bandit configuration files; Bandit excludes test directories and skips B101 (assert usage).
- **CI** (`.github/workflows/`): Added GitHub Actions CI workflow for automated QGIS plugin testing.
- **CI** (`validate_plugin.py`): Added QGIS plugin validation script checking package structure and `metadata.txt` completeness.
- **Tests** (`test_ibtool_dialog.py`): Added comprehensive unit tests for `IBToolDialog` covering step navigation, per-field status labels, validation checklist population, phase progress updates, and result-action frame visibility.
- **Tests** (`test_geometry_utils.py`): Added unit tests for `check_projection`, `polyline2`, `create_polygons_from_lines`, `extract_polygons_from_lines`, and additional `shp_area2` edge cases.
- **Tests** (`test_edge_catch_utils.py`): Added comprehensive unit tests for new helper functions — null geometry handling, `_apply_rule_parallel_close_endpoints`, `_apply_rule_all_parallel`, `_apply_rule_angle_outliers`, and merge-block behavior in `edge_catch`.
- **Tests** (`test_logger.py`): Added unit tests for `Logger` covering singleton behavior, file creation, log routing, level filtering, directory switching, `RuntimeError` handling, and message type conversion.
- **Tests** (`test_manage_directory.py`): Added unit tests for `manage_directory` covering logging, directory recreation, and exception handling.
- **Tests** (`test_check.py`): Added unit and integration tests for `InputValidator.quick_path_check` and `validate_all`.
- **Tests** (`test_import_filter.py`): Added unit tests for `_create_filter_string` covering empty list, single/multiple values, fieldname usage, and verbatim value embedding.
- **Tests** (`test_mst_clustering.py`): Added unit tests for `_main_angle`, `_near_point`, `_vector_angle`, `calc_bounding_rect`, and a debug-mode integration test for `mst_clustering`.
- **Tests** (`test_patch_remove.py`): Added integration test verifying feature-count consistency when debug mode is active.
- **Tests** (`test_ibtool.py`): Added unit tests for `apply_to_ui_elements` covering widget updates, skip behavior, and empty-value handling.

### Changed
- **Plugin** (`ibtool/ibtool.py`): Updated log levels for key processing operations from `INFO` to `CRITICAL` so they remain visible regardless of the active log-level filter. Updated copyright year.
- **Debug** (all tools): Renumbered `_DEBUG_TOOL_NAME` constants across `AddSingleBuilding.py`, `GapClose.py`, `GapFix.py`, `ImportFilter.py`, `MST_Clustering.py`, `PatchRemove.py`, and `edge_catch_utils.py` to reflect the correct pipeline call order after `EdgeCatch` was inserted as step 03.
- **Tests** (`test_ibtool_dialog.py`): Refactored `test_show_result_actions_makes_frame_visible` to use `isHidden()` instead of `isVisible()` for reliable widget-visibility assertions.
- **Tests** (`test_edge_catch_utils.py`): Expanded `test_four_parallel_lines_reduced_to_two` with detailed rule-evaluation scenarios; expanded `test_merge_block_handles_exception_gracefully` to cover additional exception-handling paths.
- **Tests** (`test_blocker.py`): Streamlined logging, improved docstrings, removed unused imports, and clarified assertions in `TestBlockerIntegration`.
- **Tests** (`test_patch_remove.py`): Renamed internal helper methods for consistency and readability.
- **Tests** (`test/__init__.py`, `test_translations.py`): Updated comments and docstrings for readability and context consistency.

### Removed
- **Docs**: Removed obsolete Sphinx documentation and build scripts.

---

## 2026-02-28

### Added
- **UI** (`ibtool/ibtool_dialog_base.ui`): Complete rewrite from absolute positioning to layout managers. New 4-step QStackedWidget stepper (Eingabe → Parameter → Validierung → Verarbeitung) with step indicator bar (stepBtn0..3). All existing objectNames preserved. New widgets: per-field `*PathStatus` labels (green ✓ / red ✗), `validationChecklist` (QListWidget with ✅/❌/⚠️), `phaseLabel`, `showFilterButton`, `copyLogButton`, `resultActionsFrame` + result action buttons. StartButton styled green, CheckButton blue.
- **UI** (`ibtool/ibtool_dialog.py`): Added `set_step()`, `set_field_status()`, `clear_field_statuses()`, `populate_validation_checklist()`, `set_phase_progress()`, `show_result_actions()`, `hide_result_actions()`, `closeEvent`/`set_close_callback()` for auto-save. Added `FilterPreviewDialog` — read-only side-by-side display of positive/negative filter entries.
- **Plugin** (`ibtool/ibtool.py`): Step navigation (`_go_prev_step`, `_go_next_step`); inline per-field path validation (`_check_path_field`) on `textChanged`; phase progress labels in `start_processing()` (6 phases with `QApplication.processEvents()`); result actions after success (`_load_result_to_qgis`, `_open_output_dir`, `_export_log`, `_show_filter_preview`); config auto-saved on dialog close; `QFileDialog`/`QApplication` added to imports; `ProcessingThread` extended with `phase_update`/`finished_ok`/`finished_error` signals. Forwarded `debug_mode` and `workspace_path` to `input_hu_filter()`, `mst_clustering()`, and `patch_remove()`; all major processing modules now support debug mode (`01_Blocker`, `02_AddSingleBuilding`, `03_EdgeCatch`, `04_GapClose`, `GapFix`, `ImportFilter`, `MST_Clustering`, `PatchRemove`).
- **Helpers** (`helpers/check.py`): Added `InputValidator.quick_path_check()` — fast filesystem existence check without QGIS layer instantiation, suitable for real-time textChanged feedback.
- **Debug** (`ibtool_tools/ImportFilter.py`): Added `debug_mode` and `workspace_path` parameters to `input_hu_filter()`; added 10 `save_debug_layer` checkpoints covering the full filter pipeline: `after_positive_filter`, `after_centroids`, `after_density_filter`, `after_density_buffer`, `after_negative_filter`, `after_neg_exclusion`, `after_dissolve`, `after_group_filter`, `after_area_filter`, `after_final_dissolve`.
- **Debug** (`ibtool_tools/MST_Clustering.py`): Added `debug_mode` and `workspace_path` parameters to `mst_clustering()`; added 5 `save_debug_layer` checkpoints: `after_mst_location_filter`, `after_hu_fid_calc`, `after_hu_centroids`, `after_location_join`, `after_clustering`.
- **Debug** (`ibtool_tools/PatchRemove.py`): Added `debug_mode` parameter to `patch_remove()` (`workspace_path` was already a required argument); added 6 `save_debug_layer` checkpoints: `after_single_parts`, `after_building_count`, `after_patch_filter`, `after_dense_blocks`, `after_dense_filter`, `after_merge`.
- **Docs** (`docs/REFACTORING.md`): Added tracking document for the ongoing refactoring roadmap.

### Changed
- **Refactor** (`ibtool_tools/PatchRemove.py`): Replaced `from qgis.core import *` with explicit imports; renamed `input_poly_sp` → `poly_single_parts`; translated German docstring to English Google-style; translated German inline comments to English; replaced `'TEMPORARY_OUTPUT'` string literals with `QgsProcessing.TEMPORARY_OUTPUT`; simplified QGIS expression strings with f-strings (removed redundant `str()` casts); removed dead commented-out code; added type hints to function signature.
- **Refactor** (`ibtool_tools/ImportFilter.py`): Extracted nested `create_filter_string()` to module-level `_create_filter_string()`; added constants `_FILTER_CODE_LENGTH`, `_MIN_DENSITY_VALUE`, `_BUFFER_CELL_DIVISOR`, `_MIN_BUILDING_AREA`; renamed PascalCase params to snake_case (`HU_Input`→`hu_layer`, `MinAreaAllBdgs`→`min_area`, `PointDensCellSize`→`cell_size`, `PointDensNbh`→`neighborhood_radius`); translated German docstring and comments to English; translated developer-facing exception messages to English; added type hints; updated test keyword argument.
- **Refactor** (`ibtool_tools/MST_Clustering.py`): Extracted three nested functions (`main_angle`, `near_point`, `vector_angle`) to private module-level functions (`_main_angle`, `_near_point`, `_vector_angle`); added named constants `_MAIN_ANGLE_MAX_DIFF`, `_BOUNDING_RECT_EXTENSION`, `_REFERENCE_VECTOR_LENGTH`; translated all German comments to English; renamed PascalCase/ALL_CAPS local variables to `snake_case`; renamed `type` parameter to `mode` (avoids builtin shadowing); added Google-style docstrings and type hints to all functions; fixed wrong `:return: None` in `mst_clustering` docstring.
- **Refactor** (`ibtool_tools/CreateMST.py`): Renamed `SpatialReference` → `spatial_reference` in backward-compat `calculate_mst()` function (naming convention); simplified compat docstring to Google-style.
- **Refactor** (`ibtool_tools/HoleClose.py`): Translated German docstring to English Google-style; translated all German inline comments to English; extracted `_OPERATOR_LESS_THAN_OR_EQUAL = 5` named constant for the QGIS `extractbyattribute` operator; added `QgsVectorLayer` type hints to function signature; added explicit `QgsVectorLayer` import.
- **Refactor** (`helpers/logger.py`): Translated all German docstrings to English Google-style; translated all German inline comments to English; renamed `startzeit` → `start_time`; translated developer-facing `ValueError` messages to English; added type hints to all methods; fixed missing space in `_qgis_level` mapping dict.
- **Refactor** (`helpers/system_utils.py`): Added `_SHAPEFILE_EXTENSIONS` named constant; translated all German docstrings and inline comments to English; fixed positional `Logger.log(msg, "LEVEL")` calls to keyword `level=`; added type hints and Google-style docstrings to all functions; removed dead commented-out example code; translated developer-facing `RuntimeError`/`FileNotFoundError` messages to English; `MIN_PYTHON`/`MAX_PYTHON`/`MIN_QGIS`/`MAX_QGIS` constants were already present.
- **Refactor** (`helpers/check.py`): Split `_check_filter_file()` (142 lines) into orchestrator + `_read_filter_file()`, `_parse_filter_sections()`, `_validate_filter_structure()`, `_validate_filter_entries()`; split `_check_params()` (112 lines) into orchestrator + `_check_numeric_params()`, `_check_spatial_reference_param()`, `_check_partition_range_params()`; removed unused `parsed` dict from `_check_numeric_params`. All user-visible German strings preserved per constraints.
- **Refactor** (`helpers/config_manager.py`): Replaced `print()` calls with `Logger.log(..., level="WARNING")`; extracted magic EPSG code `25832` to `DEFAULT_CRS_EPSG` constant in `helpers/qgis_defaults.py` and replaced all occurrences in the dataclass default and `load_config()`.
- **Refactor** (`helpers/qgis_defaults.py`): Added module-level `DEFAULT_CRS_EPSG: int = 25832` constant (UTM Zone 32N, ETRS89) for shared use across processing tools.
- **Refactor** (`helpers/data_loader.py`): Removed unused `Logger` import; extracted `COMMENT_MARKER = '#'` constant; consolidated four near-identical `select_*_file()` functions via shared `_select_shapefile()` helper; renamed parameters to `snake_case` (`Partition_layer` → `partition_layer`, `partlist` → `part_list`, etc.); simplified duplicate list-building loops into a single comprehension; translated German comments and error message to English; added Google-style docstrings and type hints.
- **Refactor** (`helpers/debug_utils.py`): Translated module docstring and all function docstrings to English Google-style; translated German log messages to English; fixed positional `Logger.log(msg, "LEVEL")` calls to keyword `level=`; extracted inline WKB type dict to module-level `_WKB_TYPE_MAP` constant; added `List`, `Optional` type hints to all function signatures.
- **Refactor** (`helpers/safe_processing.py`): Added type hints (`str`, `Dict[str, Any]`, `bool`, `Optional[str]`) to `safe_processing_run()` signature; added `typing` imports.
- **Refactor** (`helpers/geometry_utils.py`): Replaced `print()` with `Logger.log()`, translated all German docstrings/comments to English, renamed PascalCase parameters to `snake_case`, extracted `INTERSECT_BUFFER_DISTANCE = 70` constant, added Google-style docstrings and type hints to all functions.
- **Refactor** (`helpers/edge_catch_utils.py`): Extracted nested `group_lines_by_angle()` to module-level `_group_lines_by_angle()`; split `apply_filter_rules()` into four dedicated rule helpers (`_apply_rule_max_distance`, `_apply_rule_endpoint_in_rectangle`, `_apply_rule_parallel_close_endpoints`, `_apply_rule_all_parallel`, `_apply_rule_angle_outliers`); extracted filter-rule threshold constants; translated all German docstrings/comments to English; added type hints to all public functions; replaced `QgsMessageLog` calls in `create_shortest_lines_to_roads` with `Logger.log()`.
- **Refactor** (`helpers/message.py`): Added module docstring and Google-style function docstring to `msg()`; added `int` type hint to `level` parameter and `None` return type.
- **Docs** (`ai/domain/mst-architecture.md`): Updated status from "Monolithic — refactoring planned" to "Split complete"; replaced target-architecture section with documentation of the actual current structure.
- **Docs** (`docs/REFACTORING.md`): Updated "Already Clean ✓" table with all `mst/` submodules; documented completed `CreateMST` refactoring changes.
- **Docs**: Moved `CHANGELOG.md` → `docs/CHANGELOG.md`; updated references in `CLAUDE.md`.
- **Docs**: Updated `docs/contributing.md` — synced CI workflow snippet with current `.github/workflows/ci.yml` (coverage step, Codecov upload, volume mount, `main` branch trigger), added coverage-reporting section, and expanded test table to include all 33 current test files.

---

## 2026-02-27

### Added
- **Tests**: Added performance integration tests for `blocker()` (200 synthetic buildings), `footprint_density` (100 buildings across 4 blocks), and `gap_fix` (100 polygons across 2 partition groups) to establish runtime baselines and catch regressions in the core processing pipeline.
- **Tests**: Added integration tests for `patch_remove` covering GEOS validity preservation and empty building-layer edge case.
- **Tests**: Added unit tests for `IBTool.run()` orchestration in `test_ibtool.py`, verifying signal forwarding, thread lifecycle, and output-file creation.
- **Tests**: Refactored `test_create_mst.py` — replaced `print`-based error handling with `pytest.fail`; added comprehensive integration tests for MST properties (edge count, connectivity, weight ordering) and edge cases (degenerate inputs, single-node graphs).

### Changed
- **README**: Comprehensive rewrite with detailed feature descriptions, installation instructions, input data requirements, usage guides, troubleshooting tips, and citation details.
- **.gitignore**: Extended to exclude the `/ai` rule-set directory and `CLAUDE.md` from version tracking.

### Fixed
- **Logger**: Caught `RuntimeError` when appending log messages to a deleted Qt widget, preventing plugin crashes during rapid session teardown.
- **CreateMST**: Added guard against degenerate Delaunay triangulation input (fewer than 3 unique points); `scipy.spatial.Delaunay` `QhullError` is now caught and logged gracefully instead of raising an unhandled exception.
- **Package registration**: `ibtool` package is now registered dynamically to align import paths across local development, Docker, and QGIS environments, preventing `ModuleNotFoundError` caused by mismatched folder naming.

### Removed
- **ai/**: Outdated task templates and architecture rule files (`architecture-guidelines.md`, `bugfix-task.md`, `constraints.md`, `debug-mode.md`, `feature-processing.md`, `geometry-validation.md`, `mst-architecture.md`, `mst-testing.md`, `naming-conventions.md`, `new-feature-task.md`) removed from version control.

---

## 2026-02-26

### Added
- **Tests**: Added coverage for six previously untested `helpers/` modules — `test_safe_processing.py` (success path, geometry-repair flow, debug mode), `test_mst_utils.py` (`unique_items`, `rounded_edge_key`, `join_array_to_polygons`, `polygon_support_points_dict`), `test_debug_utils.py` (`_next_debug_index`, `save_debug_layer`, `save_debug_features`), `test_geometry_utils.py` (`create_empty_layer`, `create_linestring_layer_from_array`, `shp_area2`, `get_hole_polygons`), `test_edge_catch_utils.py` (five core helpers with validation); extended `test_manage_directory.py` with `save_temp_layer_to_gpkg`, `copy_shapefile`, `get_feature_count`, and `version_check` tests.
- **Tests**: Added coverage for all seven previously untested `ibtool_tools/` modules — `test_edge_catch.py` (empty road network, geometry type, debug mode), `test_patch_remove.py` (size/building-count filtering, empty building layer), `test_import_filter.py` (file-not-found, invalid layer, missing field, filter-string format, `input_hu_filter` low-count bypass), `test_gap_fix.py` (hole removal, gap bridging, area assertions, debug mode), `test_footprint_density.py` (`footprint_density` OVERLAP field, `identify_dense_blocks` threshold filtering, `calc_footprint_density` global-without-partition guard), `test_mst_clustering.py` (`calc_bounding_rect` fallback and bounding-rect cases, `mst_clustering` cluster output), `test_gap_close.py` (`gap_close_in_holes` large/small hole discrimination, `gap_close` area preservation and gap bridging).
- **Tests**: Added `test_ibtool.py` covering the main plugin module — `initialize_environment` (env-var side-effect), `ProcessingThread` (instantiation, signal presence, slot connectivity), and `IBTool` class methods (`tr`, `_collect_params` key completeness, `update_progress`, `update_messages`, `cancel_processing` idle-state guard, `load_filter_file` missing-file resilience and section parsing, `_apply_config_to_ui` early-return when no config, `_save_config_from_ui` config-manager delegation).

---

## 2026-02-25

### Added
- **EdgeCatch**: New preprocessing step `_filter_roads_near_buildings()` that splits the road network into 10 m segments, stamps a stable `seg_id` field onto each segment, buffers each segment by 25 m, and retains only segments whose buffer intersects a building footprint; matching is done via `seg_id` attribute to prevent neighbouring segments from being accidentally included.
- **EdgeCatch**: Extracted per-feature loop body into `process_single_feature()`; moved all private helpers and algorithm constants to `helpers/edge_catch_utils.py`; added `debug_mode` parameter to `edge_catch`, `filter_roads_near_buildings`, and `process_single_feature`; added `save_debug_layer` checkpoints at `road_segs_near_buildings`, `roads_selection`, `ortho_lines`, `polygons_in_block`, `result_polygons`, and `polygons_merged`; switched all `processing.run` calls in helpers to `safe_processing_run`; removed unused imports, dead inner functions, and dead constants; translated German docstrings and comments to English; fixed `polygones_merge` typo.

### Changed
- **EdgeCatch**: Per-feature `save_debug_layer` calls inside `process_single_feature()` removed — only two global checkpoints remain (`road_segs_near_buildings`, `polygons_merged`) to prevent hundreds of files being written per run; `DEBUG_TOOL_NAME` renamed to `"03_EdgeCatch"`.
- **GapClose**: `_DEBUG_TOOL_NAME` renamed from `"03_GapClose"` to `"04_GapClose"` to maintain correct call-order numbering after EdgeCatch was inserted at position 03.
- **ConfigManager**: Added `debug_mode` and `delete_part_log` boolean fields to `ProcessingConfig` with full read/write support; `_save_config_from_ui()` now also persists `SpatialReferenceBox` (as `crs_epsg`), `DebugModeBox`, and `PartLogBox`; `_apply_config_to_ui()` now restores both checkbox states on dialog open.

### Fixed
- **EdgeCatch**: `debug_mode` was not forwarded to the `edge_catch()` call in `ibtool.py`, causing all debug checkpoints to be silently skipped.
- **InputValidator**: `fkt` field values were read by numeric index (`feature[fkt_idx]`) which could resolve to a wrong field when provider and `QgsFields` orderings diverge; switched to name-based access (`feature[fkt_field]`). Buildings with `fkt = "0"` are now silently skipped instead of being flagged as ATKIS-format violations.

---

## 2026-02-24

### Added
- **safe_processing.py**: New shared helper module in `helpers/` centralising `safe_processing_run()`, eliminating duplicate definitions that previously existed in both `GapClose.py` and `GapFix.py`.

### Changed
- **GapClose**: Refactored into focused private helpers (`_dissolve_union`, `_gap_select`, `_close_block_gaps`, `_close_buffer_gaps`) so `gap_close()` is a short orchestrator; replaced all magic numbers with named module-level constants.
- **GapFix**: Removed local `safe_processing_run()` duplicate and switched to the shared `helpers/safe_processing` import.
- **AddSingleBuilding**: Refactored — translated German inline comments to English, replaced magic numbers with named module-level constants, converted docstring to Google style, and made `workspace_path` an optional keyword argument.
- **Blocker**: Refactored `blocker()` into three focused private helpers (`_build_block_polygons`, `_remove_blocks_without_buildings`, `_assign_block_names`); replaced `'TEMPORARY_OUTPUT'` string literal with `QgsProcessing.TEMPORARY_OUTPUT`; translated parameter name `strassen` → `road_network`; converted docstring to Google style; added `debug_mode`/`workspace_path` parameters and `save_debug_layer` checkpoints.
- **AddSingleBuilding**: Added `debug_mode`/`workspace_path` parameters and `save_debug_layer` checkpoints; switched all `processing.run` calls to `safe_processing_run`.
- **Blocker, AddSingleBuilding, GapClose**: Debug output folders are now numbered by pipeline call order via `_DEBUG_TOOL_NAME` constants (`01_Blocker`, `02_AddSingleBuilding`, `03_GapClose`) so folders sort chronologically.

---

## 2026-02-23

### Added
- **GapClose**: Added `Logger.log` output for feature counts of `holes_closed`, `gap_poly_max_size`, and `final_gap2` directly before the final merge so filter results are always visible in the plugin log without requiring debug mode.
- **GapClose**: Added missing `save_debug_layer` checkpoint for `holes_closed` (`07b_holes_closed`) after `native:deleteholes` in the main pipeline.

### Changed
- **GapFix**: Replaced the polygonize-based gap-fill algorithm with a buffer ring + pairwise spatial intersection approach: `fixgeometries` → hole closing (polygonize → collect → buffer(0, dissolve=True)) → singleparts with `gap_uid` → per-polygon buffer rings → pairwise ring intersection → validate → merge into the neighbour with the longest shared boundary.
- **GapClose**: Default `gap_dist` reduced from 30 m to 15 m to match empirical test results and the `gap_close_in_holes` default.
- **GapClose**: `gap_select()` now logs per-call statistics (input gap count, overlapping segments, ratio-passed, matched FIDs) so filter behaviour is traceable without debug mode.
- **system_utils**: `manage_directory()` now also deletes the `debug` folder when `del_part_log=True`, preventing stale debug files from accumulating between runs.

### Fixed
- **IBTool**: Final output was written from `merge` (the pre-GapFix layer) instead of `gap_fixed`, silently discarding all GapFix results; fixed by passing `gap_fixed` to `save_temp_layer_to_gpkg`.

---

## 2026-02-22

### Added
- **debug_utils**: Added `_next_debug_index()` helper that counts existing `.gpkg` files in the tool's debug folder to assign sequential step numbers, enabling chronological sorting in a GIS.
- **GapFix**: Added `safe_processing_run()` module-level wrapper so all four QGIS algorithm calls are covered by debug-snapshot and geometry-repair error handling.
- **GapClose**: Added `gap_close_in_holes()` function that closes gaps within holes via morphological closing (positive buffer → negative buffer, default 15 m), then removes any remaining holes smaller than `max_hole_size`.

### Changed
- **GapFix**: All four bare `processing.run()` calls replaced with `safe_processing_run()` via `_dbg` dict; the `except` block now saves the input layer as an `_err` debug snapshot when `debug_mode` is active.
- **debug_utils**: `save_debug_layer()` and `save_debug_features()` now prefix filenames with a zero-padded 3-digit index (`NNN_`) and accept an `is_error` parameter; error snapshots additionally receive the `_err` suffix.
- **GapClose**: `safe_processing_run()` now passes `is_error=True` to `save_debug_layer()` and omits the manual `_error` suffix from the step name.
- **debug-mode.md**: Fully revised to document the numbered file naming convention, checkpoint vs. error distinction, and the `is_error` parameter.
- **error-handling.md**: Updated output-path description to reflect the new `NNN_` prefix and `_err` suffix convention.

### Fixed
- **IBTool**: `debug_mode` was never forwarded to `gap_fix()` in `ibtool.py`, so no debug files were ever created despite the checkbox being active.
- **GapFix**: No intermediate results were saved during a successful run; added numbered `save_debug_layer` checkpoints after each pipeline step (`fixed`, `densified`, `lines`, `faces`, `gap_fix_result`).

---

## 2026-02-21

### Changed
- **GapFix**: Replaced the broken ArcPy-style buffer/diff approach with a topological rebuild via polygonize — pipeline is now `fixgeometries` → `densify` → `polygonstolines` → `polygonize` → classify empty faces → merge narrow gaps (< `max_gap`, default 10 m) into the neighbour with the longest shared boundary; interior rings (holes) are preserved by skipping faces that touch only one input polygon. Added `max_gap` and `debug_mode` parameters; `InputRoadnetwork` and `bufferwidth` are retained for API compatibility but no longer used.

---

## 2026-02-20

### Added
- **ConfigManager**: Integrated the existing (previously unused) `ConfigManager` into `IBTool.__init__` so `CONFIG.ini` is loaded automatically on plugin startup and all UI fields are pre-filled.
- **IBTool**: Added `_apply_config_to_ui()` method that reads `CONFIG.ini` and populates all dialog fields when `auto_load_last_used = True`.
- **IBTool**: Added `_save_config_from_ui()` method that writes the current UI state back to `CONFIG.ini`.
- **ibtool_dialog_base.ui**: Added `SaveConfigButton` to the bottom button bar for saving current UI settings to `CONFIG.ini`.
- **ProcessingConfig**: Extended with six missing settlement-analysis fields (`min_overlap_blocks`, `global_footprint_density`, `min_area`, `min_patch_size`, `max_hole_size`, `max_gap_size`).
- **docs/CONFIG.ini.example**: Documented the six new settlement-analysis parameters in the `[PROCESSING]` section.
- **docs/CONFIG_README.md**: Rewrote configuration reference in English; corrected outdated API method names; added full parameter tables.

### Changed
- **AddSingleBuilding**: Merge with `rect_merge` removed from `add_single_bdg` and delegated to the caller; the function now returns only the bounding rectangles for standalone buildings outside existing cluster polygons.

### Fixed
- **AddSingleBuilding**: `minimumboundinggeometry` incorrectly collapsed all buildings into a single bounding box because the grouping field `'node'` was not unique per feature — fixed by inserting an auto-incremental ID field before the operation.
- **AddSingleBuilding**: Replaced `native:centroids` with `native:pointonsurface` to guarantee an interior point for irregular polygon geometries.

---

## 2026-02-19

### Added
- **ibtool_dialog_base.ui**: Added `DebugModeBox` checkbox to the debug tab for enabling debug mode from the UI.

### Fixed
- **CI**: Codecov received no coverage report because container-internal paths (`/plugins/ibtool/…`) were not stripped before upload — added `sed` step to normalise paths to repo-relative form.
- **CI**: Branch trigger was set to `main` instead of `master`, so pushes to the main branch never triggered the pipeline.
- **pytest.ini**: Section header `[tool:pytest]` was invalid for `pytest.ini` — corrected to `[pytest]`; `--cov` flags removed from `addopts` to avoid failures in environments without `pytest-cov`.
- **.coveragerc**: `source` pointed to non-existent `ibtool/ibtool` subdirectory — corrected to `ibtool` (full package).

### Removed
- **Tests**: Deleted `test_mst_components.py`, `test_mst_performance_edge_cases.py`, and `test_mst_modules.py` — all tests were file-level skipped and referenced a modular MST architecture that does not yet exist.
- **Tests**: Deleted `qgis_interface.py` test helper — used deprecated QGIS 2.x API (`QgsMapLayerRegistry`) incompatible with QGIS 3.x.
- **test_create_mst**: Removed 6 skipped test methods whose skip reason was `"MST core functionality not working — returns None"`.

---

## 2026-02-17

### Fixed
- **GapClose produces empty output**: `native:dissolve` silently fails on large MultiPolygon sets (7801+ features), producing null geometry. Replaced with `native:collect` → `native:buffer(distance=0, dissolve=True)` workaround which forces a reliable GEOS union.

---

## 2025-02-07

### Added
- Input data validation system (`helpers/check.py`) with `InputValidator` class and `ValidationResult` dataclass.
- **Check button** in the plugin dialog for pre-processing validation of all input data.
- Comprehensive validation checks: file existence, layer validity, CRS match, geometry types, required fields, filter file format, output paths, minimum feature counts (HU >= 50, RN >= 30, Aux >= 10), multipart geometry detection, Part-to-HU ratio check.
- Clear success message when all checks pass; actionable error messages with hints for fixing issues.
- Start button disabled when validation errors are found; re-enabled when input paths change.

### Changed
- Replaced `check_projection()` call in `start_processing()` with comprehensive `InputValidator.validate_all()` gate.
- Processing now aborts with clear error messages if validation fails.
- Updated README with detailed input data requirements and validation documentation.

---

## 2025-01-19

### Added
- Global QGIS defaults configuration (`helpers/qgis_defaults.py`) for consistent tool behaviour.
- Modular MST architecture with specialised processors (`DelaunayProcessor`, `StreetProcessor`, `MSTCalculator`).
- Comprehensive developer guidelines and architecture preferences in `CLAUDE.md`.
- GapFix module for closing gaps between partition boundaries using QGIS processing tools.

### Changed
- **BREAKING**: Refactored `CreateMST` from a monolithic 500-line function to a modular class-based architecture.
- Simplified MST configuration: removed over-engineered config system in favour of local class constants.
- MST processors now use simple constructors without config parameters.
- Moved business logic parameters to their respective classes (`StreetProcessor.ROAD_LENGTH_THRESHOLD`, `MSTCalculator.COORDINATE_TOLERANCE`).
- Unified `Logger` usage pattern across all modules (removed `Logger = Logger()` class override pattern).
- Renamed `gapfix` → `gap_fix` for naming consistency across imports and `__all__` exports.
- Simplified file handling and layer export logic in the main plugin workflow.
- Reduced excessive logging across multiple modules for better performance and readability.

### Removed
- Obsolete nested directory structure (`ibtool/helpers/`, `ibtool/ibtool_tools/`) — 19 files.
- Duplicate root-level `ibtool.py` (935 lines, superseded by `ibtool/ibtool/ibtool.py`).
- `old_helpers/` directory containing outdated file versions.
- Unused `gapfix` imports and calls from the main plugin workflow.
- Total cleanup: ~4,700 lines of obsolete/duplicate code.

### Fixed
- Logger instantiation pattern: removed `Logger = Logger()` that was overriding the `Logger` class with an instance.
- Circular import structure: removed unused `save_temp_layer_to_gpkg` import from `geometry_utils`.
- Method naming consistency: `gapfix` → `gap_fix` throughout the codebase.
- Error logging levels in `GapClose.py` (`ERROR` → `CRITICAL` for exceptions).
