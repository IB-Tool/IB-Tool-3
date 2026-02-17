# Error Handling

## Logging System

The plugin uses a centralized logging system (`helpers/logger.py`) with four levels:

| Level | Usage |
|-------|-------|
| `CRITICAL` | Unrecoverable errors that stop processing |
| `WARNING` | Issues that allow continued processing but may affect results |
| `INFO` | Progress updates and status messages |
| `SUCCESS` | Confirmation of completed operations |

### Output Destinations

1. **UI Message Window**: Displayed in the plugin dialog's log area
2. **Log Files**: Written to `logs/logfile_YYYY-MM-DD_HH-MM-SS.txt`
3. **QGIS Message Bar**: Critical errors shown via `iface.messageBar()`

### Rules

- Always use the Logger class — never use `print()` statements
- Log level is user-configurable through the plugin UI
- Log directory is selectable through the plugin interface
- Include context (tool name, step) in log messages

## User-Facing Error Messages

### QMessageBox

Used for blocking errors that require user acknowledgment:

```python
QMessageBox.critical(self.dlg, "Error Title", "Description of what went wrong")
```

- Reserve for errors that prevent further processing
- Provide actionable information (what failed, what the user can do)

### QGIS Message Bar

Used for non-blocking warnings and status updates:

```python
iface.messageBar().pushMessage("IBTool", "Message text", level=Qgis.Warning)
```

- Use for warnings that don't stop the workflow
- Keep messages concise

## Processing Error Handling

### safe_processing_run()

The `safe_processing_run()` wrapper handles errors from QGIS Processing algorithms:

- Catches exceptions from `processing.run()`
- Logs the failed step with input parameters
- In debug mode: saves input layers to `workspace/debug/{ToolName}/` as GeoPackage

### Debug Mode

Activated via the "Fehlerhafte Features speichern" checkbox in the Debugging tab:

- Failed processing steps automatically save their input layers
- Output path: `workspace/debug/{ToolName}/{step_name}.gpkg`
- Manual debug points can be added with `save_debug_layer()` / `save_debug_features()`
- When disabled: zero overhead, no folders created

## Error Categories

| Category | Handling | Example |
|----------|----------|---------|
| Missing input | Block with QMessageBox | No HU layer selected |
| Invalid geometry | Log warning, attempt fix | Self-intersecting polygon |
| Processing failure | Log critical, save debug | Algorithm crash |
| Empty result | Log warning, continue | No features after filter |
| CRS mismatch | Block with QMessageBox | Layers in different CRS |

## Principles

1. **Never silently swallow errors** — every exception must be logged
2. **Fail fast for invalid inputs** — validate before processing
3. **Graceful degradation for processing** — log and continue where possible
4. **Debug mode for diagnostics** — save state for post-mortem analysis
