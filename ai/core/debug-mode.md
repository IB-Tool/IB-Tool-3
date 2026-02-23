# Debug Mode

Feature export on errors and at manual checkpoints for diagnosis and visual step-by-step tracing.

## Activation

Checkbox "Fehlerhafte Features speichern" in the Debugging tab of the plugin UI. When disabled: zero overhead, no folders created.

## Output Path

```
workspace/debug/{ToolName}/{NNN}_{step_name}.gpkg          ← Checkpoint
workspace/debug/{ToolName}/{NNN}_{step_name}_err.gpkg      ← Failed step
```

`NNN` is a zero-padded 3-digit index, automatically assigned by counting existing `.gpkg` files in the tool folder. The index reflects processing order and enables chronological sorting in a GIS.

### File Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Step checkpoint | `{NNN}_{step_name}.gpkg` | `001_input_buildings.gpkg` |
| Failed processing step | `{NNN}_{step_name}_err.gpkg` | `002_failed_dissolve_err.gpkg` |

- Checkpoints trace the intended processing flow (manual `save_debug_layer` calls)
- Error files mark where `safe_processing_run` caught an exception — these are the primary diagnostic target

## Central Functions (`helpers/debug_utils.py`)

| Function | Purpose |
|----------|---------|
| `save_debug_layer(layer, tool_name, step_name, workspace_path, is_error=False)` | Save an entire layer |
| `save_debug_features(features, crs, tool_name, step_name, workspace_path, fields=None, is_error=False)` | Save a feature list |

`is_error=True` appends `_err` to the filename. The step index is assigned automatically.

## Integration in Processing Tools

Tools pass `debug_mode` and `workspace_path` via a `_dbg` dict to `safe_processing_run()`:

```python
def my_tool(input_layer, crs, debug_mode=False, workspace_path=None):
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name="MyTool")

    result = safe_processing_run("native:dissolve", {
        'INPUT': input_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
```

`safe_processing_run()` automatically saves the input layers of a failed step with `is_error=True`.

## Manual Debug Checkpoints

Add a checkpoint after every meaningful processing step so the full pipeline can be traced visually in a GIS by sorting files by name:

```python
result = safe_processing_run("native:dissolve", {'INPUT': layer, ...}, **_dbg)['OUTPUT']
if debug_mode and workspace_path:
    save_debug_layer(result, "MyTool", "after_dissolve", workspace_path)
    # → workspace/debug/MyTool/001_after_dissolve.gpkg
```

Use `is_error=True` only for error cases — this is done automatically by `safe_processing_run`, but can also be used explicitly:

```python
if debug_mode and workspace_path:
    save_debug_layer(problematic_layer, "MyTool", "failed_buffer", workspace_path, is_error=True)
    # → workspace/debug/MyTool/002_failed_buffer_err.gpkg
```

## Conventions

| Parameter | Rule | Example |
|-----------|------|---------|
| `tool_name` | Class name / module name → becomes subdirectory | `"GapClose"`, `"Blocker"` |
| `step_name` | Descriptive step name, no `_error` suffix (handled via `is_error`) | `"after_dissolve"`, `"native_dissolve_INPUT"` |
| `is_error` | `True` only for failed / erroneous steps | automatic in `safe_processing_run` |

## Numbering Logic

```python
def _next_debug_index(debug_dir):
    existing = [f for f in os.listdir(debug_dir) if f.lower().endswith(".gpkg")]
    return len(existing) + 1
```

- Index resets per run (folder cleared or new workspace)
- Index is stable within a single tool execution
- Sort by filename in the GIS layer panel to follow the exact processing sequence
