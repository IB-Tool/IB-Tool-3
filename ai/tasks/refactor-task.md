# Refactor Task Template

## Purpose

Template for structural improvements in the IB-Tool 3 project. Goal: better code structure without changing business logic.

## Scope

- Improve structure and readability
- No logic changes
- Do not break existing tests
- Maintain API compatibility

## Procedure

### 1. Inventory

- [ ] Read and fully understand the current code
- [ ] Read the binding rules that apply to touched code:
  - `ai/core/constraints.md` — language rules (English for all code), named constants, no global state
  - `ai/core/naming-conventions.md` — snake_case / PascalCase / UPPER_SNAKE_CASE
  - `ai/core/debug-mode.md` — `save_debug_layer` conventions and `_dbg` dict pattern
- [ ] Identify dependencies (who uses this code?)
- [ ] Identify and run existing tests
- [ ] Define the target structure

### 2. Planning

- [ ] Break the refactoring into small, testable steps
- [ ] Determine the order (inside-out)
- [ ] Ensure backward compatibility
- [ ] Identify code to be removed
- [ ] Identify intermediate results that lack a `save_debug_layer` checkpoint

### 3. Implementation

- [ ] One step per commit
- [ ] Run tests after each step
- [ ] Update imports
- [ ] Adjust docstrings to reflect the new structure
- [ ] Translate any German comments, docstrings, or variable names in touched code to English (required by `constraints.md`)
- [ ] Add missing `save_debug_layer` checkpoints for significant intermediate results (see `ai/core/debug-mode.md` for naming conventions)

### 4. Validation

- [ ] All existing tests pass
- [ ] New tests for extracted components
- [ ] Functionality verified manually
- [ ] No orphaned imports or dead code
- [ ] No German text remains in touched code
- [ ] All significant intermediate layers have a `save_debug_layer` checkpoint
- [ ] Run `pylint <changed_module>` — no new warnings, score must not decrease

## Allowed Changes

- Extracting functions/classes
- Renaming per naming conventions
- Moving code to appropriate modules
- Removing dead code
- Adding docstrings to changed code
- Creating new modules for extracted logic
- Translating German comments, docstrings, and variable names to English in touched code
- Adding missing `save_debug_layer` checkpoints for intermediate processing results

## Forbidden Changes

- Changing business logic
- Changing algorithm parameters
- Adding new features
- Changing external behavior
- Removing or modifying existing tests (except adapting to new structure)

## Checklist

```
[ ] All existing tests pass before starting
[ ] Binding rules read (constraints.md, naming-conventions.md, debug-mode.md)
[ ] Target structure documented
[ ] Implemented step by step (not all at once)
[ ] Tests pass after each step
[ ] No logic changes
[ ] API compatibility maintained
[ ] No German text remaining in touched code
[ ] Missing save_debug_layer checkpoints added
[ ] pylint score not decreased
[ ] CHANGELOG updated
```

## Typical Refactoring Patterns in the Project

### Where to place extracted helpers

Every tool module `ibtool_tools/Foo.py` has a dedicated utils file
`helpers/foo_utils.py`.  When extracting private helpers during a refactor:

| Situation | Where to place the helper |
|---|---|
| `helpers/{toolname}_utils.py` **already exists** | Always move there — regardless of caller count |
| No utils file exists yet | Keep in the module until ≥ 2 callers share the code, then create the utils file |

**Naming rule for moved helpers:**
- Functions used only *within* the utils file itself → keep `_` prefix
- Functions explicitly imported by the owner tool module → **no** `_` prefix
  (they are intentionally cross-module; the leading underscore would mislead)

**Example:**
```
helpers/edge_catch_utils.py
  _normalize_node()              # internal to utils — keep _
  _build_minimized_lines(...)    # internal to utils — keep _
  filter_roads_near_buildings()  # imported by EdgeCatch.py — no _
  process_single_feature()       # imported by EdgeCatch.py — no _
```

### Splitting a monolithic function

```
Before: one_large_function(a, b, c, d, e)  # 500+ lines
After:
  - ClassA.step_1(a, b)
  - ClassB.step_2(c)
  - Orchestrator.execute(a, b, c, d, e)  # delegates
```

### Parameters to class constants

```
Before: function(x, threshold=50, buffer=5)
After:
  class Processor:
      THRESHOLD = 50
      BUFFER = 5
      def process(self, x): ...
```
