# Debug-Modus

Feature-Export bei Fehlern für Diagnose und Reproduktion.

## Aktivierung

Checkbox "Fehlerhafte Features speichern" im Debugging-Tab der Plugin-UI. Bei Deaktivierung: kein Overhead, keine Ordner.

## Ausgabepfad

```
workspace/debug/{ToolName}/{step_name}.gpkg
```

## Zentrale Funktionen (`helpers/debug_utils.py`)

| Funktion | Zweck |
|----------|-------|
| `save_debug_layer(layer, tool_name, step_name, workspace_path)` | Speichert einen ganzen Layer |
| `save_debug_features(features, crs, tool_name, step_name, workspace_path)` | Speichert eine Feature-Liste |

## Integration in Processing-Tools

Tools leiten `debug_mode` und `workspace_path` über ein `_dbg`-Dict an `safe_processing_run()` weiter:

```python
def my_tool(input_layer, crs, debug_mode=False, workspace_path=None):
    _dbg = dict(debug_mode=debug_mode, workspace_path=workspace_path, tool_name="MyTool")

    result = safe_processing_run("native:dissolve", {
        'INPUT': input_layer,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }, **_dbg)['OUTPUT']
```

`safe_processing_run()` speichert bei Fehler + Debug-Modus automatisch die Input-Layer des fehlgeschlagenen Schritts.

## Manuelle Debug-Punkte

```python
if debug_mode and workspace_path:
    save_debug_layer(problematic_layer, "MyTool", "after_dissolve", workspace_path)
```

## Konventionen

| Parameter | Regel | Beispiel |
|-----------|-------|----------|
| `tool_name` | Klassenname/Modulname → wird zum Unterordner | `"GapClose"`, `"Blocker"` |
| `step_name` | Beschreibender Schritt → wird zum Dateinamen | `"invalid_after_dissolve"` |
