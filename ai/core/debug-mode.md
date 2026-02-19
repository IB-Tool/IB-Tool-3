# Debug Mode

Feature export on errors for diagnosis and reproduction.

## Activation

Checkbox "Fehlerhafte Features speichern" in the Debugging tab of the plugin UI. When disabled: zero overhead, no folders created.

## Output Path

```
workspace/debug/{ToolName}/{step_name}.gpkg
```

## Central Functions (`helpers/debug_utils.py`)

| Function | Purpose |
|----------|---------|
| `save_debug_layer(layer, tool_name, step_name, workspace_path)` | Save an entire layer |
| `save_debug_features(features, crs, tool_name, step_name, workspace_path)` | Save a feature list |

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

`safe_processing_run()` automatically saves the input layers of a failed step when debug mode is active.

## Manual Debug Points

```python
if debug_mode and workspace_path:
    save_debug_layer(problematic_layer, "MyTool", "after_dissolve", workspace_path)
```

## Conventions

| Parameter | Rule | Example |
|-----------|------|---------|
| `tool_name` | Class name / module name → becomes subdirectory | `"GapClose"`, `"Blocker"` |
| `step_name` | Descriptive step → becomes file name | `"invalid_after_dissolve"` |
