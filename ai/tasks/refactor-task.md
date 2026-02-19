# Refactor Task Template

## Purpose

Template for structural improvements in the IBTool project. Goal: better code structure without changing business logic.

## Scope

- Improve structure and readability
- No logic changes
- Do not break existing tests
- Maintain API compatibility

## Procedure

### 1. Inventory

- [ ] Read and fully understand the current code
- [ ] Identify dependencies (who uses this code?)
- [ ] Identify and run existing tests
- [ ] Define the target structure

### 2. Planning

- [ ] Break the refactoring into small, testable steps
- [ ] Determine the order (inside-out)
- [ ] Ensure backward compatibility
- [ ] Identify code to be removed

### 3. Implementation

- [ ] One step per commit
- [ ] Run tests after each step
- [ ] Update imports
- [ ] Adjust docstrings to reflect the new structure

### 4. Validation

- [ ] All existing tests pass
- [ ] New tests for extracted components
- [ ] Functionality verified manually
- [ ] No orphaned imports or dead code

## Allowed Changes

- Extracting functions/classes
- Renaming per naming conventions
- Moving code to appropriate modules
- Removing dead code
- Adding docstrings to changed code
- Creating new modules for extracted logic

## Forbidden Changes

- Changing business logic
- Changing algorithm parameters
- Adding new features
- Changing external behavior
- Removing or modifying existing tests (except adapting to new structure)

## Checklist

```
[ ] All existing tests pass before starting
[ ] Target structure documented
[ ] Implemented step by step (not all at once)
[ ] Tests pass after each step
[ ] No logic changes
[ ] API compatibility maintained
[ ] CHANGELOG updated
```

## Typical Refactoring Patterns in the Project

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
