# New Feature Task Template

## Purpose

Template for implementing new functionality in the IB-Tool 3 project. Goal: clean integration without affecting existing functionality.

## Scope

- Encapsulate the new feature cleanly
- Do not break the existing API
- Add documentation
- Write tests for the new feature

## Procedure

### 1. Requirements Clarification

- [ ] Fully understand the feature requirements
- [ ] Define input and output data
- [ ] Define boundaries: what does NOT belong to this feature?
- [ ] Identify dependencies on existing modules

### 2. Architecture

- [ ] Where in the project tree does the feature belong?
- [ ] New tool in `ibtool_tools/`? New helper in `helpers/`?
- [ ] Define interfaces to existing modules
- [ ] Determine parameters (class constants vs. QGIS defaults)

### 3. Implementation

- [ ] Create module with a clear responsibility
- [ ] Stateless processing function (input → output)
- [ ] Logging via the Logger system
- [ ] Error handling with `safe_processing_run()`
- [ ] Debug mode support (`_dbg` dict)

### 4. Integration

- [ ] Import in `ibtool/ibtool.py` (absolute imports)
- [ ] UI binding in the dialog if needed
- [ ] Log messages for progress and errors

### 5. Validation

- [ ] Unit tests for the new module
- [ ] Integration tests in the overall workflow
- [ ] Existing tests unchanged and passing
- [ ] Geometry validation in tests
- [ ] Run `pylint <new_module>` — no warnings, score must not decrease

### 6. Documentation

- [ ] Docstrings for all new functions/classes
- [ ] Update CHANGELOG.md
- [ ] Update CLAUDE.md if architecture changes

## Allowed Changes

- New module in `ibtool_tools/` or `helpers/`
- Import of the new module in `ibtool/ibtool.py`
- UI extension in the dialog (new widgets, tabs)
- New test file in `test/`
- CHANGELOG and CLAUDE.md updates

## Forbidden Changes

- Changing the existing public API
- Modifying existing tool functionality
- New external dependencies without prior consultation
- Modifying existing tests (except adding new ones)

## Checklist

```
[ ] Requirements clearly defined
[ ] Architectural decision documented
[ ] Feature cleanly encapsulated
[ ] Stateless processing function
[ ] Debug mode supported
[ ] Unit tests written
[ ] Existing tests pass
[ ] pylint score not decreased
[ ] CHANGELOG updated
[ ] Ready for code review
```

## Module Template

```python
"""
ModuleName — Short description.

This module implements [feature description].
"""

from .helpers.logger import Logger

logger = Logger()


class FeatureName:
    """Description of the class."""

    # Algorithm parameters
    PARAMETER_NAME = 42.0  # Description and unit

    def process(self, input_layer, crs, debug_mode=False, workspace_path=None):
        """Main processing function.

        Args:
            input_layer: QgsVectorLayer with input data
            crs: QgsCoordinateReferenceSystem
            debug_mode: Enable debug features
            workspace_path: Path for debug output

        Returns:
            QgsVectorLayer with the result
        """
        _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path,
                     tool_name="FeatureName")
        # Processing...
```
