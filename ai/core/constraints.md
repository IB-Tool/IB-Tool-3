# Constraints

Binding rules for all code changes in the IB-Tool 3 project.

For release-specific constraints (metadata.txt, LICENSE, ZIP packaging, CI),
see [release-conventions.md](release-conventions.md).

## Language

| Content Type | Language | Examples |
|---|---|---|
| Code (comments, docstrings, variable names) | **English** | `# Calculate buffer distance`, `"""Returns the MST edges."""` |
| Developer documentation (`ai/`, `docs/`, `CLAUDE.md`) | **English** | All markdown files for AI/developer context |
| Commit messages, CHANGELOG (technical) | **English** | `Fix dissolve bug on large MultiPolygon sets` |
| UI strings (via `QCoreApplication.translate()`) | **German** (primary), English (fallback) | Dialog labels, message bar text |
| Log messages visible to end-users | **German** | Logger output in plugin UI |

When modifying existing code or documentation, apply these language rules to the parts you touch. Do not leave German comments or docstrings in code you are editing.

## Interface Access

- **No direct access to `iface`** outside the main class (`ibtool/ibtool.py`) and dialog (`ibtool_dialog.py`)
- Processing tools (`ibtool_tools/`) never receive `iface` as a parameter
- Tools communicate results via return values, not UI calls

## Variables and State

- **No global variables** — all state is passed as parameters or held as class attributes
- Processing tools must be **stateless**
- No side effects outside the defined scope of a function
- No modification of input parameters (input layers, feature lists)

## Documentation

- **Every new function** gets a Google-style docstring
- **Every new class** gets a docstring describing its purpose
- Parameters with non-obvious meaning are explained in the docstring

## Paths and Configuration

- **No hardcoded paths** — all paths via parameters or `config_manager.py`
- Workspace path is set by the user through the UI
- Temporary files via `QgsProcessing.TEMPORARY_OUTPUT`

## Dependencies

- **No new dependencies** without prior consultation
- Allowed libraries: numpy, scipy, sklearn, networkx, pandas, matplotlib, geopandas, shapely
- QGIS-native modules (qgis.core, qgis.analysis, processing) unrestricted

## Numeric Values

- **No magic numbers** — all constants must be named and documented
- Algorithm-specific parameters defined as class constants
- QGIS technical parameters centralized in `helpers/qgis_defaults.py`

## Error Handling

- Every `processing.run()` operation must catch errors
- Critical errors: log `CRITICAL` and abort processing
- Unexpected situations (e.g. geometry repair triggered): log `WARNING` and continue
- Normal processing outcomes (progress, counts, empty results): log `INFO`
- In debug mode: save intermediate results
- **Always pass `level=` explicitly to `Logger.log()`** — the default is `"WARNING"`, which is misleading for status messages

## Strings

- All user-visible strings must be translatable via `QCoreApplication.translate()`
- Internal log messages may be in English or German (German preferred for end-user-visible logs)
