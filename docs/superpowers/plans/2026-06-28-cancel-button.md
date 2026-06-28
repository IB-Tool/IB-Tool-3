# Cancel Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "Abbrechen" button close the dialog when idle and abort processing between phases when running.

**Architecture:** Add a `ProcessingCancelledError` exception and two boolean flags (`_is_processing`, `_cancel_requested`) to `IBTool`. `_update_phase()` raises the exception when the flag is set; `start_processing()` catches it. `cancel_processing()` either closes the dialog (idle) or sets the flag (running).

**Tech Stack:** Python, PyQt5, pytest, unittest.mock

---

### Task 1: Add `ProcessingCancelledError` and state flags

**Files:**
- Modify: `ibtool/ibtool/ibtool.py:77` (module level, after `_open_directory`)
- Modify: `ibtool/ibtool/ibtool.py:145-156` (`__init__`, after `_last_output_folder`)
- Test: `test/test_ibtool.py`

- [ ] **Step 1: Write failing tests**

Add after the existing `TestIBTool.test_cancel_processing_does_not_crash` test (around line 165):

```python
@pytest.mark.unit
def test_initial_is_processing_false(self):
    """_is_processing must be False after construction."""
    tool = _make_tool()
    assert tool._is_processing is False

@pytest.mark.unit
def test_initial_cancel_requested_false(self):
    """_cancel_requested must be False after construction."""
    tool = _make_tool()
    assert tool._cancel_requested is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest test/test_ibtool.py::TestIBTool::test_initial_is_processing_false test/test_ibtool.py::TestIBTool::test_initial_cancel_requested_false -v
```

Expected: `AttributeError: 'IBTool' object has no attribute '_is_processing'`

- [ ] **Step 3: Add `ProcessingCancelledError` at module level**

In `ibtool/ibtool/ibtool.py`, after the `_open_directory` function (around line 93), add:

```python
class ProcessingCancelledError(Exception):
    """Raised inside start_processing() when the user requests cancellation."""
```

- [ ] **Step 4: Add flags to `__init__`**

In `ibtool/ibtool/ibtool.py`, after the `self._last_output_folder = ""` line (around line 147), add:

```python
# Processing state flags for cancel support
self._is_processing: bool = False
self._cancel_requested: bool = False
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest test/test_ibtool.py::TestIBTool::test_initial_is_processing_false test/test_ibtool.py::TestIBTool::test_initial_cancel_requested_false -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```
git add ibtool/ibtool/ibtool.py test/test_ibtool.py
git commit -m "feat: add ProcessingCancelledError and cancellation state flags"
```

---

### Task 2: Update `cancel_processing()`

**Files:**
- Modify: `ibtool/ibtool/ibtool.py:166-168`
- Test: `test/test_ibtool.py:158-165`

- [ ] **Step 1: Update existing test and add two new tests**

Replace the existing `test_cancel_processing_does_not_crash` test (lines 158-165) with:

```python
# --- cancel_processing ---

@pytest.mark.unit
def test_cancel_processing_when_idle_closes_dialog(self):
    """cancel_processing when not processing must close the dialog."""
    tool = _make_tool()
    tool._is_processing = False
    tool.dlg.close = MagicMock()

    tool.cancel_processing()

    tool.dlg.close.assert_called_once()

@pytest.mark.unit
def test_cancel_processing_when_running_sets_flag(self):
    """cancel_processing when processing must set _cancel_requested and show message."""
    tool = _make_tool()
    tool._is_processing = True
    tool._cancel_requested = False
    tool.dlg.MessageBox.clear()

    tool.cancel_processing()

    assert tool._cancel_requested is True
    assert "Abbruch" in tool.dlg.MessageBox.toPlainText()

@pytest.mark.unit
def test_cancel_processing_when_running_does_not_close_dialog(self):
    """cancel_processing when processing must not close the dialog."""
    tool = _make_tool()
    tool._is_processing = True
    tool.dlg.close = MagicMock()

    tool.cancel_processing()

    tool.dlg.close.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest test/test_ibtool.py::TestIBTool::test_cancel_processing_when_idle_closes_dialog test/test_ibtool.py::TestIBTool::test_cancel_processing_when_running_sets_flag test/test_ibtool.py::TestIBTool::test_cancel_processing_when_running_does_not_close_dialog -v
```

Expected: FAIL (current implementation does neither)

- [ ] **Step 3: Replace `cancel_processing()` implementation**

In `ibtool/ibtool/ibtool.py`, replace lines 166-168:

```python
def cancel_processing(self):
    """Close the dialog when idle; request abort between phases when processing."""
    if not self._is_processing:
        self.dlg.close()
    else:
        self._cancel_requested = True
        self.update_messages("Abbruch wird nach dem aktuellen Schritt durchgeführt...")
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest test/test_ibtool.py::TestIBTool::test_cancel_processing_when_idle_closes_dialog test/test_ibtool.py::TestIBTool::test_cancel_processing_when_running_sets_flag test/test_ibtool.py::TestIBTool::test_cancel_processing_when_running_does_not_close_dialog -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add ibtool/ibtool/ibtool.py test/test_ibtool.py
git commit -m "feat: implement cancel_processing with idle-close and running-abort logic"
```

---

### Task 3: Update `_update_phase()` to raise on cancel

**Files:**
- Modify: `ibtool/ibtool/ibtool.py:1067-1070`
- Test: `test/test_ibtool.py` (class `TestUpdatePhase`, around line 1286)

- [ ] **Step 1: Add a failing test to `TestUpdatePhase`**

Add after the last existing test in `TestUpdatePhase` (after line 1323):

```python
@pytest.mark.unit
def test_raises_processing_cancelled_error_when_cancel_requested(self):
    """Must raise ProcessingCancelledError after processEvents if _cancel_requested is True."""
    from ibtool.ibtool.ibtool import ProcessingCancelledError

    self.tool._cancel_requested = True
    try:
        with patch.object(self.tool.dlg, "set_phase_progress"):
            with pytest.raises(ProcessingCancelledError):
                self.tool._update_phase(3, 6, "Calculate MST", 40)
    finally:
        self.tool._cancel_requested = False  # reset for other tests

@pytest.mark.unit
def test_does_not_raise_when_cancel_not_requested(self):
    """Must not raise when _cancel_requested is False."""
    from ibtool.ibtool.ibtool import ProcessingCancelledError

    self.tool._cancel_requested = False
    with patch.object(self.tool.dlg, "set_phase_progress"):
        self.tool._update_phase(3, 6, "Calculate MST", 40)  # must not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest test/test_ibtool.py::TestUpdatePhase::test_raises_processing_cancelled_error_when_cancel_requested test/test_ibtool.py::TestUpdatePhase::test_does_not_raise_when_cancel_not_requested -v
```

Expected: first test FAIL (no exception raised), second PASS

- [ ] **Step 3: Update `_update_phase()` implementation**

In `ibtool/ibtool/ibtool.py`, replace lines 1067-1070:

```python
def _update_phase(self, phase: int, total: int, name: str, percent: int) -> None:
    """Update the phase progress indicator and flush pending UI events."""
    self.dlg.set_phase_progress(phase, total, name, percent)
    QApplication.processEvents()
    if self._cancel_requested:
        raise ProcessingCancelledError()
```

- [ ] **Step 4: Run all `TestUpdatePhase` tests**

```
pytest test/test_ibtool.py::TestUpdatePhase -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```
git add ibtool/ibtool/ibtool.py test/test_ibtool.py
git commit -m "feat: raise ProcessingCancelledError in _update_phase when cancel requested"
```

---

### Task 4: Wrap `start_processing()` in try/except/finally

**Files:**
- Modify: `ibtool/ibtool/ibtool.py:1244-1437`

No new tests needed here — the integration is covered by the existing `_update_phase` tests and the state-flag tests from Tasks 1-3. The try/except/finally is mechanical wiring.

- [ ] **Step 1: Set flags at the start of `start_processing()`**

In `ibtool/ibtool/ibtool.py`, the method starts at line 1244. After the docstring (around line 1261), the first executable line is `self.dlg.set_step(3)`. Add the flag resets **before** that line:

```python
self._cancel_requested = False
self._is_processing = True
```

So the block reads:

```python
self._cancel_requested = False
self._is_processing = True
# Navigate to the processing page and reset UX state
self.dlg.set_step(3)
```

- [ ] **Step 2: Wrap the processing body in try/except/finally**

The full method body (from `self.dlg.set_step(3)` down to the final `logger.log(...)` at line 1437) must be wrapped. The structure:

```python
self._cancel_requested = False
self._is_processing = True
try:
    # Navigate to the processing page and reset UX state
    self.dlg.set_step(3)
    # ... all existing code unchanged ...
    logger.log("Processing completed successfully.", level="CRITICAL")
except ProcessingCancelledError:
    self.update_messages("Verarbeitung abgebrochen.")
    logger.log("Verarbeitung durch Nutzer abgebrochen.", level="WARNING")
finally:
    self._is_processing = False
```

Apply this by:
1. Adding one level of indentation (4 spaces) to every line from `self.dlg.set_step(3)` to the end of the method
2. Inserting `try:` before `self.dlg.set_step(3)`
3. Appending the `except` and `finally` blocks after the last line of the try body

- [ ] **Step 3: Run the full test suite**

```
pytest test/test_ibtool.py -v
```

Expected: all previously passing tests still PASS; no regressions

- [ ] **Step 4: Commit**

```
git add ibtool/ibtool/ibtool.py
git commit -m "feat: wrap start_processing in try/except/finally for cancellation support"
```
