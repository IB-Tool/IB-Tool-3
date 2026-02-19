---
description: Use this skill when the user asks to write, create, or improve documentation or docstrings for a module, function, or class — for example "dokumentiere GapFix", "write docs for the blocker", "add docstrings to X", "Doku ergänzen", "fehlende Docstrings hinzufügen". Invoke automatically whenever a documentation task is identified for this QGIS plugin project.
---

# /write-docs — Write Documentation for an IBTool Module

Write documentation for the module: **$ARGUMENTS**

Follow these steps in order. Do not skip any step.

---

## Step 1 — Read the target module

Search for `$ARGUMENTS` in these locations (in order):
- `ibtool_tools/$ARGUMENTS.py`
- `helpers/$ARGUMENTS.py`
- `ibtool/$ARGUMENTS.py`
- Try case/name variations as needed

Read the file completely. Identify:
- All public classes and their purpose
- All public methods: parameters, return values, side effects
- Error handling behavior (what is caught, what is raised, what is logged)
- Any calls to `processing.run()` or `safe_processing_run()`
- Constants and their meaning

## Step 2 — Consult project rules (mandatory)

Read these files before writing anything:
- `ai/core/constraints.md` — language rules (English for code/docs, German only for UI strings), docstring format
- `ai/core/naming-conventions.md` — abbreviations, naming patterns
- `docs/error-handling.md` — how to document error behavior

## Step 3 — Write Google-style docstrings

Add or update docstrings directly in the module source file for every class and every public method that is missing one or has an incomplete one.

### Docstring format

```python
def function_name(param1: type, param2: type) -> return_type:
    """Short one-line summary (imperative, ends with period).

    Longer description if needed. Explain the algorithm or approach
    at a high level. Mention side effects.

    Args:
        param1: Description. Include units if applicable (e.g., meters).
        param2: Description.

    Returns:
        Description of what is returned, including type info if
        not obvious from the annotation.

    Raises:
        ValueError: When param1 is None or empty.
        QgsProcessingException: If the underlying algorithm fails.

    Example:
        >>> result = function_name(layer, 10.0)
        >>> assert result is not None
    """
```

### Rules
- Language: **English** (never German in docstrings or code)
- First line: short imperative phrase, ends with a period
- Args block: one line per parameter, colon-separated
- Raises block: only for errors that callers need to handle
- Example block: only if usage is non-obvious

## Step 4 — Decide whether a Markdown doc is needed

**Create a new Markdown file** if the module:
- Is a new or recently added tool in `ibtool_tools/`
- Has complex domain logic not yet described in `docs/` or `ai/domain/`
- Contains non-obvious workarounds or known limitations

**Extend an existing file** if the module's topic is already covered.

**Skip Markdown** if the module is a simple helper and docstrings suffice.

### Where to put the Markdown file

| Content type | Location | Filename pattern |
|---|---|---|
| Architecture, data flow, design | `docs/` | `kebab-case.md` |
| Domain knowledge, known bugs, pitfalls | `ai/domain/` | `kebab-case.md` |
| Project-wide rules, constraints | `ai/core/` | `kebab-case.md` |

### Markdown document structure

```markdown
# Module Name

## Overview
One paragraph: what it does, when to use it, what problem it solves.

## Architecture / Design
How it fits into the plugin. Diagram if helpful (text-based).

## Key Functions / Classes
Brief reference table + description for each public API.

## Usage Example
```python
# Minimal working example
```

## Known Issues / Limitations
Document any workarounds, edge cases, performance limits.

## Related Files
- `ai/domain/related-topic.md`
- `docs/related-architecture.md`
```

### Cross-link requirement
New docs must be linked from `CLAUDE.md` (in the relevant table) and from `docs/plugin-architecture.md` if architecturally significant.

## Step 5 — Update CHANGELOG.md

Add a line under the `[Unreleased]` section:
```
- Docs: Added/updated documentation for `$ARGUMENTS`
```

## Step 6 — Output

Report:
1. List of functions/classes where docstrings were added or updated
2. Path of the Markdown file created or extended (or reason why none was needed)
3. Whether CHANGELOG.md was updated
4. Any open questions about behavior that should be clarified with the developer
