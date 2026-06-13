"""
Tests for ibtool_tools/GapFix.py.

The module exposes one public function:

  gap_fix(Inputpoly, InputRoadnetwork=None, workspace_path=None,
          bufferwidth=70, max_gap=10.0,
          erosion_width=None, linearity_area_fraction=0.7,
          debug_mode=False)

Algorithm under test:
  Step 0:  Fix geometries
  Step 1:  Dissolve adjacent polygons (collect + buffer(0)); interior holes
           are preserved and pass through unchanged
  Step 2:  Singleparts + gap_uid
  Step 3:  Buffer rings (buffer - originals)
  Step 4:  Pairwise ring intersections (split MultiPolygon parts) → gap zones
  Step 5:  Validate gap zones (must touch both source polygons)
  Step 5b: Linearity filter via erosion + area-fraction
  Step 6:  Merge linear gap zones into adjacent polygon (longer shared boundary)

Unit tests cover (no Processing — path branches that return early):
  - empty/zero-feature layer → returns input unchanged
  - invalid layer → returns input unchanged

Integration tests cover:
  - returns a valid QgsVectorLayer
  - result geometries are not null
  - polygon with interior hole → hole is removed
  - two adjacent polygons with a small gap → gap_uid field is present
  - two polygons closer than 2×max_gap → total area increases (gap filled)
  - debug_mode=True does not raise
"""

import pytest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsWkbTypes,
)
from PyQt5.QtCore import QVariant

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.GapFix import gap_fix


# ---------------------------------------------------------------------------
# Domain-specific geometry helpers (not shared)
# ---------------------------------------------------------------------------

def _square_with_hole(outer: float, hx: float, hy: float, hole: float) -> QgsGeometry:
    """Outer square with an interior square hole."""
    outer_ring = [
        QgsPointXY(0,     0),     QgsPointXY(outer, 0),
        QgsPointXY(outer, outer), QgsPointXY(0,     outer),
        QgsPointXY(0,     0),
    ]
    hole_ring = [
        QgsPointXY(hx,        hy),
        QgsPointXY(hx + hole, hy),
        QgsPointXY(hx + hole, hy + hole),
        QgsPointXY(hx,        hy + hole),
        QgsPointXY(hx,        hy),
    ]
    return QgsGeometry.fromPolygonXY([outer_ring, hole_ring])


def _total_area(layer: QgsVectorLayer) -> float:
    """Sum of geometry areas of all features."""
    return sum(
        f.geometry().area()
        for f in layer.getFeatures()
        if f.geometry() and not f.geometry().isNull() and not f.geometry().isEmpty()
    )


# ---------------------------------------------------------------------------
# TestGapFixEarlyReturn — unit tests (no Processing)
# ---------------------------------------------------------------------------

class TestGapFixEarlyReturn:
    """Unit tests for gap_fix edge cases that trigger early returns."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_returns_input_unchanged(self):
        """gap_fix on a valid but empty layer must return the input layer."""
        layer = make_polygon_layer()    # 0 features

        result = gap_fix(layer)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_invalid_layer_returns_input(self):
        """gap_fix on an invalid QgsVectorLayer must return early without crashing."""
        invalid_layer = QgsVectorLayer()    # uninitialised

        result = gap_fix(invalid_layer)

        assert result is not None


# ---------------------------------------------------------------------------
# TestGapFixIntegration — integration tests (uses QGIS Processing)
# ---------------------------------------------------------------------------

class TestGapFixIntegration:
    """Integration tests for GapFix.gap_fix."""

    # --- basic validity ---

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """gap_fix returns a non-None, valid QgsVectorLayer."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_fix(layer)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_has_at_least_one_feature(self):
        """Non-empty input must produce at least one output feature."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_fix(layer)

        assert result.featureCount() > 0

    @pytest.mark.integration
    def test_no_null_or_empty_geometries_in_result(self):
        """No null or empty geometries in the output."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_fix(layer)

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),  f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry at FID {feat.id()}"

    @pytest.mark.integration
    def test_result_geometries_are_geos_valid(self):
        """All output geometries must pass GEOS validity check."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_fix(layer)

        for feat in result.getFeatures():
            geom = feat.geometry()
            if not geom.isNull() and not geom.isEmpty():
                assert geom.isGeosValid(), \
                    f"Invalid geometry at FID {feat.id()}: {geom.validateGeometry()}"

    # --- interior holes ---

    @pytest.mark.integration
    def test_interior_hole_is_preserved(self):
        """Interior holes pass through ``gap_fix`` unchanged.

        Hole closing was removed from GapFix and is handled elsewhere in
        the pipeline. The input area must therefore be preserved.

        Setup:
          100 × 100 outer square  = 10 000 m²
          20 × 20 hole at (40,40) =    400 m²
          Input area              =  9 600 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, _square_with_hole(outer=100, hx=40, hy=40, hole=20))
        input_area = _total_area(layer)  # ≈ 9 600

        result = gap_fix(layer)

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.05), (
            f"Expected hole to be preserved (area unchanged), "
            f"got {result_area:.1f} vs {input_area:.1f}"
        )

    @pytest.mark.integration
    def test_solid_polygon_area_unchanged(self):
        """A solid polygon (no holes, no gaps) passes through with the same area.

        Setup: 100 × 100 = 10 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))
        input_area = _total_area(layer)

        result = gap_fix(layer)

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.05), \
            f"Expected area unchanged, got {result_area:.1f} vs {input_area:.1f}"

    # --- gap closing ---

    @pytest.mark.integration
    def test_gap_uid_field_present_in_result(self):
        """Output layer must contain a 'gap_uid' field."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(108, 0, 100))

        result = gap_fix(layer, max_gap=10)

        field_names = [f.name() for f in result.fields()]
        assert "gap_uid" in field_names, \
            f"Expected 'gap_uid' field; found: {field_names}"

    @pytest.mark.integration
    def test_two_polygons_with_small_gap_area_increases(self):
        """Two polygons closer than 2 × max_gap have their gap filled.

        Setup:
          Square 1: [0,   0, 100, 100]  = 10 000 m²
          Square 2: [108, 0, 208, 100]  = 10 000 m²
          Gap:      8 m wide  × 100 m   =    800 m²
          max_gap = 10  →  2×10=20 > 8  →  gap is bridged

        Expected total output area ≈ 10 000 + 10 000 + 800 = 20 800 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(108, 0, 100))
        input_area = _total_area(layer)  # 20 000

        result = gap_fix(layer, max_gap=10)

        result_area = _total_area(result)
        assert result_area > input_area, \
            f"Expected area to increase (gap filled), " \
            f"got {result_area:.1f} <= {input_area:.1f}"

    @pytest.mark.integration
    def test_two_polygons_with_large_gap_not_filled(self):
        """Polygons farther than 2 × max_gap apart are NOT merged.

        Setup:
          Square 1: [0,   0, 100, 100]
          Square 2: [150, 0, 250, 100]
          Gap:      50 m wide
          max_gap = 10  →  2×10=20 < 50  →  gap NOT bridged
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(150, 0, 100))
        input_area = _total_area(layer)  # 20 000

        result = gap_fix(layer, max_gap=10)

        result_area = _total_area(result)
        # Area should NOT significantly increase
        assert result_area == pytest.approx(input_area, rel=0.05), \
            f"Expected area unchanged (gap too wide), " \
            f"got {result_area:.1f} vs {input_area:.1f}"

    # --- linearity filter (Step 5b) ---

    @pytest.mark.integration
    def test_thin_corridor_merged_with_default_filter(self):
        """Default linearity params merge a very thin (3 m) linear corridor.

        Setup:
          Square 1: [0,   0, 100, 100]
          Square 2: [103, 0, 203, 100]
          Gap zone: ≈ 3 m wide × 100 m tall
        With erosion_width = max_gap/2 = 5, the 3 m strip vanishes completely
        → frac_removed = 1.0 ≥ 0.7 → linear → merged.
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(103, 0, 100))
        input_area = _total_area(layer)

        result = gap_fix(layer, max_gap=10)

        result_area = _total_area(result)
        assert result_area > input_area, (
            f"Thin linear corridor should be merged, "
            f"got {result_area:.1f} vs {input_area:.1f}"
        )

    @pytest.mark.integration
    def test_zero_erosion_width_keeps_gaps_open(self):
        """erosion_width=0 ⇒ nothing vanishes ⇒ frac_removed=0 < 0.7 ⇒ no merge.

        Demonstrates that the filter actively rejects gap zones when configured
        strictly. Same geometry as the existing small-gap test, where the gap
        WOULD be filled under legacy behaviour.
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(108, 0, 100))
        input_area = _total_area(layer)  # 20 000

        result = gap_fix(layer, max_gap=10, erosion_width=0.0)

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.01), (
            f"erosion_width=0 must keep all gaps open, "
            f"got {result_area:.1f} vs {input_area:.1f}"
        )

    @pytest.mark.integration
    def test_zero_area_fraction_reproduces_legacy_behaviour(self):
        """linearity_area_fraction=0.0 disables the filter (legacy behaviour).

        Even with `erosion_width=0` (frac_removed=0), the predicate
        `0 >= 0.0` is True, so every valid gap zone passes — same as before
        Step 5b existed.
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(108, 0, 100))
        input_area = _total_area(layer)  # 20 000

        result = gap_fix(
            layer, max_gap=10,
            erosion_width=0.0, linearity_area_fraction=0.0,
        )

        result_area = _total_area(result)
        assert result_area > input_area, (
            f"linearity_area_fraction=0.0 must merge all valid gaps, "
            f"got {result_area:.1f} <= {input_area:.1f}"
        )

    @pytest.mark.integration
    def test_explicit_erosion_width_overrides_default(self):
        """Explicit erosion_width is honoured instead of max_gap/2.

        With a deliberately tiny `erosion_width=0.1`, a moderate 8 m gap is
        eroded by only 0.1 m on each side. frac_removed ≈ 0.025 < 0.7 → the
        gap is classified as blocky and stays open, even though it would be
        merged with the default `erosion_width = max_gap/2 = 5`.
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 100))
        add_feature_to_layer(layer, make_square_geom(108, 0, 100))
        input_area = _total_area(layer)

        result = gap_fix(layer, max_gap=10, erosion_width=0.1)

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.01), (
            f"Explicit erosion_width=0.1 must keep the moderate gap open, "
            f"got {result_area:.1f} vs {input_area:.1f}"
        )

    @pytest.mark.integration
    def test_branching_gap_zone_merged_with_defaults(self):
        """Three close polygons creating a branching (Y / T) gap zone.

        Three 50 × 50 squares arranged so that pairwise narrow gaps meet —
        the combined empty space between them branches. The Step 5b filter
        is local (erosion) and must accept every branch individually, so the
        total polygon area must grow.

        Layout (5 m gaps between adjacent squares):
            A = [0,   0,  50,  50]
            B = [55,  0,  105, 50]
            C = [27,  55, 77,  105]
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,  0,  50))
        add_feature_to_layer(layer, make_square_geom(55, 0,  50))
        add_feature_to_layer(layer, make_square_geom(27, 55, 50))
        input_area = _total_area(layer)  # 3 × 2 500 = 7 500

        result = gap_fix(layer, max_gap=10)

        result_area = _total_area(result)
        assert result_area > input_area, (
            f"Branching narrow gap zone should be merged, "
            f"got {result_area:.1f} <= {input_area:.1f}"
        )

    # --- debug mode ---

    @pytest.mark.integration
    def test_debug_mode_does_not_crash(self, tmp_path):
        """gap_fix with debug_mode=True must not raise an exception."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_fix(layer, workspace_path=str(tmp_path), debug_mode=True)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_performance_with_100_block_partition(self):
        """gap_fix completes within 30 s for 100 polygon blocks in two partition groups.

        Group A: 50 polygons in a 10×5 grid with 2 m internal gaps.
        Group B: 50 polygons offset 300 m to the right (gap too wide to fill).
        """
        import time

        layer = make_polygon_layer()
        # Group A: 50 polygons in a 10×5 grid (20×20 m each, 2 m gap between them)
        for i in range(50):
            x = float((i % 10) * 22)
            y = float((i // 10) * 22)
            add_feature_to_layer(layer, make_square_geom(x, y, 20))
        # Group B: 50 polygons with a 300 m gap to group A (not filled by gap_fix)
        for i in range(50):
            x = float(300 + (i % 10) * 22)
            y = float((i // 10) * 22)
            add_feature_to_layer(layer, make_square_geom(x, y, 20))

        assert layer.featureCount() == 100

        start = time.time()
        result = gap_fix(layer, max_gap=5.0)
        elapsed = time.time() - start

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert elapsed < 30, f"gap_fix took {elapsed:.1f} s (limit: 30 s)"
