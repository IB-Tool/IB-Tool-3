# Cancel Button — Design Spec

**Date:** 2026-06-28
**Branch:** FIX_german_ui

## Goal

The "Abbrechen" button in the IBTool dialog should:
- **When idle:** close the dialog immediately
- **When processing:** abort the run between phases, keep the dialog open for the user to close manually

## Constraints

- Processing runs synchronously on the main thread
- `QApplication.processEvents()` is called inside `_update_phase()` after each of the 6 phases
- True mid-phase cancellation is not required — between phases is sufficient

## Design

### New fields on `IBTool`

```python
self._is_processing: bool = False
self._cancel_requested: bool = False
```

### New exception

```python
class ProcessingCancelledError(Exception):
    pass
```

Defined at module level in `ibtool.py`.

### `cancel_processing()` (replaces current no-op)

```python
def cancel_processing(self):
    if not self._is_processing:
        self.dlg.close()
    else:
        self._cancel_requested = True
        self.update_messages("Abbruch wird nach dem aktuellen Schritt durchgeführt...")
```

### `_update_phase()` — add cancel check

After the existing `processEvents()` call:

```python
def _update_phase(self, phase, total, name, percent):
    self.dlg.set_phase_progress(phase, total, name, percent)
    QApplication.processEvents()
    if self._cancel_requested:
        raise ProcessingCancelledError()
```

### `start_processing()` — wrap in try/except/finally

```python
def start_processing(self):
    self._cancel_requested = False
    self._is_processing = True
    try:
        # ... existing processing logic ...
    except ProcessingCancelledError:
        self.update_messages("Verarbeitung abgebrochen.")
    finally:
        self._is_processing = False
```

## Behaviour Summary

| State | Click "Abbrechen" | Result |
|-------|-------------------|--------|
| Idle | immediate | dialog closes |
| Processing | deferred | current phase finishes, then abort; dialog stays open |

## Out of Scope

- Immediate mid-phase cancellation (would require QThread)
- Partial result saving on cancel
