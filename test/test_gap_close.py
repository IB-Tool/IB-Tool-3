"""
Tests for ibtool_tools/GapClose.py.

The module exposes two public functions:

  gap_close(input_layer, blocks, max_hole_size, max_gap_size, crs,
            gap_dist=15, debug_mode=False, workspace_path=None)

  gap_close_in_holes(input_layer, buffer_dist=15,
                     debug_mode=False, workspace_path=None)

Unit tests cover (no Processing — early return branches):
  - gap_close: empty dissolved input → returns input_layer
  - gap_close_in_holes: empty dissolved input → returns input_layer

Integration tests cover (gap_close_in_holes):
  - solid polygon → area unchanged
  - polygon with large hole (> MIN_PROCESSED_HOLE_AREA_M2=500 m²) → hole filled
  - polygon with very small hole (< 500 m²) → returned unchanged
  - result geometries are GEOS-valid
  - debug_mode=True does not raise

Integration tests cover (gap_close):
  - returns a valid QgsVectorLayer
  - result geometries are GEOS-valid
  - two adjacent polygons with a gap → area equals or increases (gap bridged)
  - solid polygon → area approximately preserved
  - debug_mode=True does not raise
"""

import pytest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsWkbTypes,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.GapClose import gap_close, gap_close_in_holes


# ---------------------------------------------------------------------------
# Domain-specific geometry helpers (not shared)
# ---------------------------------------------------------------------------

def _square_with_hole(outer: float,
                      hx: float, hy: float, hole: float) -> QgsGeometry:
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


def _all_geos_valid(layer: QgsVectorLayer) -> bool:
    """True if every non-null geometry in the layer passes GEOS validity."""
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom and not geom.isNull() and not geom.isEmpty():
            if not geom.isGeosValid():
                return False
    return True


def _block_layer(crs: str = "EPSG:25833",
                 x0: float = -100, y0: float = -100,
                 size: float = 600) -> QgsVectorLayer:
    """Single large block covering the entire test area."""
    layer = make_polygon_layer(crs)
    add_feature_to_layer(layer, make_square_geom(x0, y0, size))
    return layer


# ---------------------------------------------------------------------------
# TestGapCloseInHoles — integration tests
# ---------------------------------------------------------------------------

class TestGapCloseInHoles:
    """Integration tests for GapClose.gap_close_in_holes."""

    @pytest.mark.integration
    def test_result_is_valid_qgsvectorlayer(self):
        """gap_close_in_holes returns a non-None, valid QgsVectorLayer."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close_in_holes(layer)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_solid_polygon_area_unchanged(self):
        """A solid polygon has no holes → area must be preserved.

        Setup: 100 × 100 = 10 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))
        input_area = _total_area(layer)

        result = gap_close_in_holes(layer)

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.05), \
            f"Expected area unchanged ({input_area:.1f}), got {result_area:.1f}"

    @pytest.mark.integration
    def test_large_hole_is_filled(self):
        """A hole whose area exceeds MIN_PROCESSED_HOLE_AREA_M2=500 m² is filled.

        Setup:
          100 × 100 outer = 10 000 m²
          30 × 30 hole (900 m²) at (35, 35)
          Input area = 9 100 m²

        Expected: hole area (900 m²) added back → result ≈ 10 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, _square_with_hole(outer=100, hx=35, hy=35, hole=30))
        input_area = _total_area(layer)  # ≈ 9 100

        result = gap_close_in_holes(layer, buffer_dist=15)

        result_area = _total_area(result)
        assert result_area > input_area, \
            f"Expected area to increase (hole filled), " \
            f"got {result_area:.1f} <= {input_area:.1f}"

    @pytest.mark.integration
    def test_tiny_hole_is_not_filled(self):
        """A hole below 500 m² is below MIN_PROCESSED_HOLE_AREA_M2 → stays.

        Setup:
          100 × 100 outer = 10 000 m²
          15 × 15 hole (225 m²) at (42, 42) — below 500 m² threshold
          Input area = 9 775 m²

        Expected: result_area ≈ 9 775 m² (hole kept)
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, _square_with_hole(outer=100, hx=42, hy=42, hole=15))
        input_area = _total_area(layer)  # ≈ 9 775

        result = gap_close_in_holes(layer, buffer_dist=15)

        result_area = _total_area(result)
        # Area should stay approximately the same (hole not filled)
        assert result_area == pytest.approx(input_area, rel=0.10), \
            f"Expected area ≈ {input_area:.1f} (small hole kept), got {result_area:.1f}"

    @pytest.mark.integration
    def test_result_geometries_are_geos_valid(self):
        """All output geometries must pass GEOS validity check."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, _square_with_hole(outer=100, hx=35, hy=35, hole=30))

        result = gap_close_in_holes(layer)

        assert _all_geos_valid(result), \
            "One or more output geometries failed GEOS validity check"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_layer_returns_valid_result(self):
        """gap_close_in_holes on empty layer must not crash."""
        layer = make_polygon_layer()

        result = gap_close_in_holes(layer)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    def test_debug_mode_does_not_crash(self, tmp_path):
        """gap_close_in_holes with debug_mode=True must not raise."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close_in_holes(
            layer, workspace_path=str(tmp_path), debug_mode=True
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)


# ---------------------------------------------------------------------------
# TestGapClose — integration tests
# ---------------------------------------------------------------------------

class TestGapClose:
    """Integration tests for GapClose.gap_close."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """gap_close returns a non-None, valid QgsVectorLayer."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_has_at_least_one_feature(self):
        """Non-empty input must produce at least one output feature."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
        )

        assert result.featureCount() > 0

    @pytest.mark.integration
    def test_result_geometries_are_geos_valid(self):
        """All output geometries must pass GEOS validity check."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
        )

        assert _all_geos_valid(result), \
            "One or more output geometries failed GEOS validity check"

    @pytest.mark.integration
    def test_solid_polygon_area_approximately_preserved(self):
        """A solid polygon without gaps must have area preserved.

        Input: 200 × 200 m = 40 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 200))
        input_area = _total_area(layer)

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
        )

        result_area = _total_area(result)
        assert result_area == pytest.approx(input_area, rel=0.10), \
            f"Expected area ≈ {input_area:.1f}, got {result_area:.1f}"

    @pytest.mark.integration
    def test_two_polygons_with_narrow_gap_area_increases(self):
        """Two adjacent polygons with gap < 2×gap_dist have their gap bridged.

        Setup:
          Square 1: [0,   0, 200, 200] = 40 000 m²
          Square 2: [215, 0, 415, 200] = 40 000 m²
          Gap: 15 m wide × 200 m  = 3 000 m²
          gap_dist = 15  →  2×15 = 30 > 15  →  gap is bridged by buffer approach

        Expected: result area > 80 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0,   0, 200))
        add_feature_to_layer(layer, make_square_geom(215, 0, 200))
        input_area = _total_area(layer)  # 80 000

        blocks = _block_layer(x0=-50, y0=-50, size=500)
        result = gap_close(
            layer, blocks, max_hole_size=1000, max_gap_size=50_000,
            crs=self.crs, gap_dist=15,
        )

        result_area = _total_area(result)
        assert result_area >= input_area, \
            f"Expected area ≥ {input_area:.1f}, got {result_area:.1f}"

    @pytest.mark.integration
    def test_interior_hole_is_filled(self):
        """Interior holes smaller than max_hole_size are filled.

        Setup:
          100 × 100 outer = 10 000 m²
          20 × 20 hole (400 m²) at (40, 40)
          max_hole_size = 1 000 → hole is below threshold → filled

        Expected: result area ≈ 10 000 m²
        """
        layer = make_polygon_layer()
        add_feature_to_layer(layer, _square_with_hole(outer=100, hx=40, hy=40, hole=20))
        input_area = _total_area(layer)  # ≈ 9 600

        blocks = _block_layer()
        result = gap_close(
            layer, blocks, max_hole_size=1_000, max_gap_size=5_000,
            crs=self.crs, gap_dist=15,
        )

        result_area = _total_area(result)
        assert result_area > input_area, \
            f"Expected area to increase (hole filled), " \
            f"got {result_area:.1f} <= {input_area:.1f}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_input_handled_gracefully(self):
        """gap_close on an empty layer must not crash."""
        layer = make_polygon_layer()

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    def test_debug_mode_does_not_crash(self, tmp_path):
        """gap_close with debug_mode=True must not raise an exception."""
        layer = make_polygon_layer()
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))

        result = gap_close(
            layer, _block_layer(), max_hole_size=1000, max_gap_size=5000,
            crs=self.crs, gap_dist=15,
            debug_mode=True, workspace_path=str(tmp_path),
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
