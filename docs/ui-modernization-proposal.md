# UI Modernization Proposals for IB-Tool

This document outlines concrete proposals for making the plugin's currently functional user interface more modern, clearer, and more efficient.

## 1) Simplify the information architecture

- **Split the workflow into 4 steps** instead of showing all fields at once:
  1. Input data
  2. Parameters
  3. Validation
  4. Execution & results
- Use an **accordion or stepper layout** so users only see the currently relevant section.
- **Highlight the primary action**: visually prioritize "Check" and "Start" (primary/secondary button logic).

## 2) Introduce a modern visual design system

- Use **consistent spacing (8-pt grid)** for a calmer layout.
- Define a clear **typography hierarchy**:
  - Section titles (larger/bold)
  - Field labels (medium)
  - Help text (small/gray)
- Apply **semantic status colors consistently**:
  - Green = valid/ok
  - Yellow = notice/warning
  - Red = error
  - Blue = running process
- Use softer grouping via **cards/frames** instead of hard boxes.

## 3) Improve form usability

- Add **inline feedback for path fields** immediately after selection (file exists, layer type is correct, required field exists).
- Provide **context-sensitive helper text** under critical inputs (e.g., HU/RN requirements).
- Set **sensible defaults** for frequently used parameters (e.g., known CRS values or recently used directories).
- **Mark invalid fields directly** (red border + specific field-level error message instead of global messages only).

## 4) Improve validation and error communication

- Show validation results as a **checklist**:
  - ✅ HU loaded
  - ❌ RN contains multipart geometries
  - ⚠️ Part:HU ratio is near the limit
- Write error messages in a **solution-oriented way** ("Run `multiparttosingleparts` on RN layer first").
- Add **"fix-it" links** to docs or named QGIS tools directly in messages.

## 5) Modernize processing UX

- Visualize progress by **processing phases** (e.g., 1/6 load data, 2/6 block derivation, ...).
- Add a **live log with filters** (Info/Warn/Error) plus a "Copy" button for support.
- Improve **cancel/recovery flow** with clear states and hints about already-created intermediate outputs.
- Add a **post-run results panel** with direct actions:
  - Load result into QGIS
  - Open working directory
  - Export log

## 6) Interaction patterns for power users

- Add **preset profiles** (e.g., "Standard", "Quick test", "High accuracy").
- Allow **save/load parameter sets** as JSON/INI.
- Show **recently used inputs** in a history list.
- Ensure **keyboard-friendly navigation** (tab order, Enter triggers primary action).

## 7) Accessibility and robustness

- Improve contrast (also for dark QGIS themes).
- Never use icons without a text label.
- Add tooltips for domain terms (BCR, MST, EdgeCatch).
- Ensure responsive behavior in smaller dialog sizes (scrollable areas instead of clipped fields).

## 8) Concrete quick wins (low effort, high impact)

1. Visually differentiate "Check" and "Start" and place them consistently.
2. Show validation errors near the affected fields instead of only in global message boxes.
3. Upgrade progress from "percent only" to "phase + percent".
4. Add a validation checklist to the dialog.
5. Persist last-used paths and parameter values.

## 9) Suggested implementation roadmap

- **Sprint 1 (UI clarity):** structure layout, typography/spacing, and primary action hierarchy.
- **Sprint 2 (Validation UX):** field-level errors, checklist, improved error text.
- **Sprint 3 (Processing UX):** phase progress, log panel, result actions.
- **Sprint 4 (Power features):** presets, import/export, history.

## 10) Measurable success indicators

- Reduced pre-run drop-offs after "Check" by X%.
- Shorter time to first successful run.
- Fewer support requests related to input/path errors.
- Higher reuse rate of saved presets.
