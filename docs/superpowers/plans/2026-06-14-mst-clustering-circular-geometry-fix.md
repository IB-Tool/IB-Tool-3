# MST Clustering — Circular Geometry Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter arc-segment edges of circular building parts from the dominant-angle calculation in `mst_clustering()` so that rectangular buildings in a cluster are correctly oriented.

**Architecture:** Extract a private helper `_filter_short_edges()` that drops edges shorter than 20 % of the longest edge per building. Integrate it as a single dict-comprehension after `dict_hu` is built in `mst_clustering()`. No changes to `calc_bounding_rect()` or `_main_angle()`.

**Tech Stack:** Python 3.11+, numpy (already imported), no new dependencies.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `ibtool/ibtool_tools/MST_Clustering.py` | New constant `_MIN_EDGE_LENGTH_RATIO`, new function `_filter_short_edges()`, one-line integration in `mst_clustering()` |
| Modify | `test/test_mst_clustering.py` | New `TestFilterShortEdges` class (3 unit tests), update import |

---

## Task 1: Write failing tests for `_filter_short_edges`

**Files:**
- Modify: `test/test_mst_clustering.py`

- [ ] **Step 1: Add `_filter_short_edges` to the import at the top of the test file**

  Existing import block (lines 41–44):
  ```python
  from ibtool.ibtool_tools.MST_Clustering import (
      calc_bounding_rect, mst_clustering,
      _main_angle, _near_point, _vector_angle,
  )
  ```
  Replace with:
  ```python
  from ibtool.ibtool_tools.MST_Clustering import (
      calc_bounding_rect, mst_clustering,
      _main_angle, _near_point, _vector_angle,
      _filter_short_edges,
  )
  ```

- [ ] **Step 2: Append the new test class to the end of `test/test_mst_clustering.py`**

  ```python
  # ---------------------------------------------------------------------------
  # TestFilterShortEdges — unit tests (pure Python, no QGIS)
  # ---------------------------------------------------------------------------

  class TestFilterShortEdges:
      """Unit tests for MST_Clustering._filter_short_edges."""

      @pytest.mark.unit
      def test_arc_edges_below_threshold_are_removed(self):
          """Edges shorter than 20 % of the longest edge are excluded.

          Mixed building: rectangular walls (20–50 m) + arc segments (4 m).
          Threshold = 0.20 × 50 m = 10 m  →  arc edges filtered out.
          """
          long_edges = [
              [0.0,  0.0, 50.0,  0.0, 50.0],
              [50.0, 0.0, 50.0, 20.0, 20.0],
              [50.0, 20.0, 0.0, 20.0, 50.0],
              [0.0, 20.0,  0.0,  0.0, 20.0],
          ]
          arc_edges = [
              [0.0, 0.0, 2.0, 3.5, 4.0],
              [2.0, 3.5, 4.5, 6.5, 4.0],
          ]
          result = _filter_short_edges(long_edges + arc_edges)
          assert result == long_edges

      @pytest.mark.unit
      def test_equal_length_edges_are_all_kept(self):
          """Pure circle: all equal-length edges pass the filter unchanged.

          For a circle approximated with N segments, every edge has the same
          length, so all are >= 20 % of max  →  none are dropped.
          """
          import math
          r, n = 20.0, 36
          circle_edges = []
          for i in range(n):
              a1 = 2 * math.pi * i / n
              a2 = 2 * math.pi * (i + 1) / n
              x1, y1 = r * math.cos(a1), r * math.sin(a1)
              x2, y2 = r * math.cos(a2), r * math.sin(a2)
              length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
              circle_edges.append([x1, y1, x2, y2, length])
          result = _filter_short_edges(circle_edges)
          assert result == circle_edges

      @pytest.mark.unit
      @pytest.mark.edge_case
      def test_fallback_when_fewer_than_two_edges_would_survive(self):
          """When only one edge passes the threshold, all edges are returned.

          This guards against leaving a polygon with a single edge, which
          would break the bounding-rect calculation.
          """
          edges = [
              [0.0, 0.0, 100.0, 0.0, 100.0],   # 100 % of max  →  passes
              [0.0, 0.0,   5.0, 0.0,   5.0],   #   5 % of max  →  filtered
              [0.0, 0.0,   8.0, 0.0,   8.0],   #   8 % of max  →  filtered
          ]
          # After filter: only 1 edge survives  →  fallback returns all 3
          result = _filter_short_edges(edges)
          assert result == edges
  ```

- [ ] **Step 3: Run the tests and verify they fail with ImportError**

  ```
  docker run --rm qgis-plugin-test pytest test/test_mst_clustering.py::TestFilterShortEdges -v
  ```
  Expected output contains:
  ```
  ImportError: cannot import name '_filter_short_edges' from 'ibtool.ibtool_tools.MST_Clustering'
  ```

---

## Task 2: Implement `_filter_short_edges` and wire it into `mst_clustering()`

**Files:**
- Modify: `ibtool/ibtool_tools/MST_Clustering.py`

- [ ] **Step 1: Add the new module-level constant after the existing constants (after line 37)**

  Existing block (lines 30–37):
  ```python
  # Maximum angle difference (degrees) for two angles to be grouped into the same cluster.
  _MAIN_ANGLE_MAX_DIFF = 10

  # Extension length (map units) for constructing the oriented reference axis in bounding rect calc.
  _BOUNDING_RECT_EXTENSION = 10_000

  # Length of the horizontal reference vector used when measuring line orientation angles.
  _REFERENCE_VECTOR_LENGTH = 100
  ```
  Replace with:
  ```python
  # Maximum angle difference (degrees) for two angles to be grouped into the same cluster.
  _MAIN_ANGLE_MAX_DIFF = 10

  # Extension length (map units) for constructing the oriented reference axis in bounding rect calc.
  _BOUNDING_RECT_EXTENSION = 10_000

  # Length of the horizontal reference vector used when measuring line orientation angles.
  _REFERENCE_VECTOR_LENGTH = 100

  # Minimum edge length as a fraction of the longest edge per building.
  # Edges below this ratio are arc segments of circular geometry parts and are
  # excluded from the dominant-angle pool to prevent orientation bias.
  _MIN_EDGE_LENGTH_RATIO = 0.20
  ```

- [ ] **Step 2: Add the `_filter_short_edges` function after the `_vector_angle` function (after line 171)**

  After the closing of `_vector_angle` (line 171, `return ang`), insert:
  ```python


  def _filter_short_edges(edge_rows: list[list]) -> list[list]:
      """Return only edges whose length meets the minimum ratio threshold.

      Removes arc-segment noise from circular building parts while preserving
      straight edges of rectangular shapes. Falls back to the full list when
      fewer than two edges would survive (e.g. degenerate single-edge polygon).

      Args:
          edge_rows: List of ``[x1, y1, x2, y2, length]`` rows for one building.

      Returns:
          Filtered list, or the original list if the filter would leave fewer
          than two edges.
      """
      if not edge_rows:
          return edge_rows
      max_len = max(row[4] for row in edge_rows)
      threshold = max_len * _MIN_EDGE_LENGTH_RATIO
      filtered = [row for row in edge_rows if row[4] >= threshold]
      return filtered if len(filtered) >= 2 else edge_rows
  ```

- [ ] **Step 3: Integrate the filter into `mst_clustering()` — one line after `dict_hu` is built**

  Existing line in `mst_clustering()` (line 414):
  ```python
  dict_hu = dict(list(hu_line_array))
  ```
  Replace with:
  ```python
  dict_hu = dict(list(hu_line_array))
  dict_hu = {fid: _filter_short_edges(rows) for fid, rows in dict_hu.items()}
  ```

---

## Task 3: Run all tests and commit

- [ ] **Step 1: Run the new unit tests and verify they pass**

  ```
  docker run --rm qgis-plugin-test pytest test/test_mst_clustering.py::TestFilterShortEdges -v
  ```
  Expected:
  ```
  test_arc_edges_below_threshold_are_removed  PASSED
  test_equal_length_edges_are_all_kept        PASSED
  test_fallback_when_fewer_than_two_edges_would_survive  PASSED
  ```

- [ ] **Step 2: Run the full MST Clustering test suite to check for regressions**

  ```
  docker run --rm qgis-plugin-test pytest test/test_mst_clustering.py -v
  ```
  Expected: all previously passing tests still pass.

- [ ] **Step 3: Commit**

  ```bash
  git add ibtool/ibtool_tools/MST_Clustering.py test/test_mst_clustering.py
  git commit -m "fix: exclude arc segments of circular buildings from MST orientation angle"
  ```
