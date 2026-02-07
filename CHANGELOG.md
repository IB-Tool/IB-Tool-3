# Changelog

All notable changes to IBTool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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