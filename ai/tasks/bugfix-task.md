# Bugfix Task Template

## Purpose

Template for bug fixes in the IBTool project. Goal: minimal, targeted changes to resolve the reported issue.

## Scope

- Fix only the reported bug
- No side refactoring
- No code improvements outside the affected area
- No new features

## Procedure

### 1. Analysis

- [ ] Fully understand the bug report
- [ ] Locate and read the affected code
- [ ] Identify a reproduction scenario
- [ ] Determine the root cause (not just the symptom)

### 2. Impact Analysis

- [ ] Which other modules use the affected code?
- [ ] Can the fix have side effects?
- [ ] Are there existing tests for the affected area?

### 3. Implementation

- [ ] Minimal change to fix the bug
- [ ] Follow existing code conventions
- [ ] Update docstrings if necessary
- [ ] Add logger messages for new error paths

### 4. Validation

- [ ] Existing tests still pass (no regression)
- [ ] New test for the fixed bug
- [ ] For geometry fixes: validity and multipart checks
- [ ] Debug mode tested (if processing-related)
- [ ] Run `pylint <changed_module>` — no new warnings, score must not decrease

### 5. Documentation

- [ ] Update CHANGELOG.md
- [ ] Commit message clearly describes the fix

## Allowed Changes

- Bug fix in the affected module
- New test for the fix
- CHANGELOG entry
- Docstring adjustments in the changed code

## Forbidden Changes

- Renaming variables/functions outside the fix area
- Adding imports not needed for the fix
- Refactoring adjacent functions
- Changing the public API
- Adding new dependencies

## Checklist

```
[ ] Root cause identified
[ ] Fix is minimal and targeted
[ ] No regression in existing tests
[ ] New test covers the bug
[ ] pylint score not decreased
[ ] CHANGELOG updated
[ ] Ready for code review
```
