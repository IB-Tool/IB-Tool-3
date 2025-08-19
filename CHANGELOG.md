# Changelog

All notable changes to IBTool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Global QGIS defaults configuration (`helpers/qgis_defaults.py`) for consistent tool behavior
- Modular MST architecture with specialized processors (DelaunayProcessor, StreetProcessor, MSTCalculator)
- Comprehensive developer guidelines and architecture preferences in CLAUDE.md

### Changed
- **BREAKING**: Refactored CreateMST from monolithic 500-line function to modular class-based architecture
- Simplified MST configuration: removed over-engineered config system in favor of local class constants
- MST processors now use simple constructors without config parameters
- Moved business logic parameters to their respective classes (StreetProcessor.ROAD_LENGTH_THRESHOLD, MSTCalculator.COORDINATE_TOLERANCE)

### Fixed
- Eliminated code duplication in MST parameter definitions
- Improved separation of concerns between technical QGIS parameters and business logic
- Enhanced testability through modular component design

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