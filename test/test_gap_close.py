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

from qgis import processing  # noqa: E402
from unittest.mock import patch

from ibtool.helpers import overlay_utils
from ibtool.helpers.overlay_utils import symmetrical_difference, polygon_parts
from ibtool.ibtool_tools.GapClose import gap_close, gap_close_in_holes, TOPOLOGY_GRID_SIZE


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


# ---------------------------------------------------------------------------
# symmetrical_difference — must reproduce qgis:symmetricaldifference exactly
# ---------------------------------------------------------------------------

def _poly(wkt: str) -> QgsGeometry:
    return QgsGeometry.fromWkt(wkt)


def _symdiff_inputs():
    """Blocks (with BLOCK_ID) and one settlement polygon (with id/name).

    Covers: partial overlap, block fully covered (empty difference), block
    without contact, multipart block, off-grid coordinates, settlement with a
    hole, block touching the settlement only along an edge. All geometries are
    valid (the pipeline runs fixgeometries before the sym-diff).
    """
    blocks = QgsVectorLayer("Polygon?crs=EPSG:25833&field=BLOCK_ID:integer", "blocks", "memory")
    block_geoms = [
        "Polygon ((0 0, 100 0, 100 100, 0 100, 0 0))",                         # partial
        "Polygon ((150 0, 230 0, 230 70, 150 70, 150 0))",                     # fully covered
        "Polygon ((600 0, 700 0, 700 100, 600 100, 600 0))",                   # no contact
        "MultiPolygon (((300 0, 340 0, 340 40, 300 40, 300 0)),"
        "((360 60, 400 60, 400 100, 360 100, 360 60)))",                      # multipart
        "Polygon ((250.00000123 120, 300.4567891 120, 300.4567891 180, 250.00000123 180,"
        " 250.00000123 120))",                                                # partial, off-grid
        "Polygon ((330.33333 100, 360 100, 360 150, 330.33333 150, 330.33333 100))",  # edge only
    ]
    feats = []
    for i, wkt in enumerate(block_geoms, start=1):
        f = QgsFeature(blocks.fields())
        f.setGeometry(_poly(wkt))
        f["BLOCK_ID"] = i
        feats.append(f)
    blocks.dataProvider().addFeatures(feats)

    settlement = QgsVectorLayer("Polygon?crs=EPSG:25833&field=id:integer&field=name:string",
                                "settlement", "memory")
    f = QgsFeature(settlement.fields())
    geom = _poly(
        "Polygon ((50 -20, 250 -20, 250 20, 380 20, 380 80, 330.33333 80, 330.33333 180,"
        " 250 180, 250 80, 50 80, 50 -20),"
        "(120 30, 135 30, 135 45, 120 45, 120 30))")
    assert geom.isGeosValid()
    f.setGeometry(geom)
    f["id"] = 7
    f["name"] = "settlement"
    settlement.dataProvider().addFeatures([f])
    return blocks, settlement


def _as_rows(layer):
    return [(f.geometry().asWkt(17), [None if v is None or (hasattr(v, "isNull") and v.isNull())
                                     else v for v in f.attributes()])
            for f in layer.getFeatures()]


class TestSymmetricalDifference:
    """symmetrical_difference replaces qgis:symmetricaldifference in
    _close_block_gaps. It computes the overlay union once instead of once per
    input feature (21 s → 0.5 s on the largest sample partition) and must
    produce exactly the same features, attributes and order."""

    @pytest.mark.integration
    def test_identical_to_qgis_algorithm(self):
        blocks, settlement = _symdiff_inputs()
        expected = processing.run("qgis:symmetricaldifference", {
            "INPUT": blocks, "OVERLAY": settlement,
            "OUTPUT": "memory:", "GRID_SIZE": TOPOLOGY_GRID_SIZE})["OUTPUT"]

        actual = symmetrical_difference(blocks, settlement, TOPOLOGY_GRID_SIZE)

        assert [f.name() for f in actual.fields()] == [f.name() for f in expected.fields()]
        assert actual.wkbType() == expected.wkbType()
        assert _as_rows(actual) == _as_rows(expected)
        assert actual.featureCount() > 0

    @pytest.mark.integration
    def test_identical_with_swapped_inputs(self):
        blocks, settlement = _symdiff_inputs()
        expected = processing.run("qgis:symmetricaldifference", {
            "INPUT": settlement, "OVERLAY": blocks,
            "OUTPUT": "memory:", "GRID_SIZE": TOPOLOGY_GRID_SIZE})["OUTPUT"]

        actual = symmetrical_difference(settlement, blocks, TOPOLOGY_GRID_SIZE)

        assert _as_rows(actual) == _as_rows(expected)

    @pytest.mark.unit
    def test_overlay_union_computed_once_per_overlay_group(self):
        """All blocks intersect the same single settlement feature → one union
        for that direction, not one per block."""
        blocks, settlement = _symdiff_inputs()
        calls = []
        real_union = overlay_utils.grid_union

        def counting_union(geoms, params):
            calls.append(len(geoms))
            return real_union(geoms, params)

        with patch.object(overlay_utils, "grid_union", side_effect=counting_union):
            symmetrical_difference(blocks, settlement, TOPOLOGY_GRID_SIZE)

        # blocks − settlement: 1 union (same settlement for all intersecting
        # blocks); settlement − blocks: 1 union
        assert len(calls) == 2, calls


class TestPolygonParts:
    """Grid differences can return a GeometryCollection (polygons plus collapsed
    line/point remnants). Like qgis:symmetricaldifference, the polygon parts
    must be kept (in order) — not the whole feature dropped. Found on sample
    partition PART_56 (two blocks lost, 5,940 m² different result)."""

    @pytest.mark.unit
    def test_collection_keeps_polygon_parts_in_order(self):
        geom = QgsGeometry.fromWkt(
            "GeometryCollection (Polygon ((0 0, 10 0, 10 10, 0 10, 0 0)),"
            " LineString (20 0, 30 0),"
            " Polygon ((40 0, 50 0, 50 5, 40 5, 40 0)),"
            " Point (60 0))")
        result = polygon_parts(geom)
        assert result.asWkt(0) == (
            "MultiPolygon (((0 0, 10 0, 10 10, 0 10, 0 0)),((40 0, 50 0, 50 5, 40 5, 40 0)))")

    @pytest.mark.unit
    def test_zero_area_polygon_part_is_kept(self):
        """QGIS keeps degenerate polygon parts; dropping them would change the WKT."""
        geom = QgsGeometry.fromWkt(
            "GeometryCollection (Polygon ((0 0, 10 0, 10 10, 0 10, 0 0)),"
            " Polygon ((20 0, 30 0, 25 0, 20 0)), LineString (40 0, 50 0))")
        assert polygon_parts(geom).constGet().numGeometries() == 2

    @pytest.mark.unit
    def test_collection_without_polygons_returns_none(self):
        geom = QgsGeometry.fromWkt("GeometryCollection (LineString (0 0, 1 0), Point (5 5))")
        assert polygon_parts(geom) is None

    @pytest.mark.unit
    def test_polygon_is_returned_as_multipolygon_unchanged(self):
        geom = QgsGeometry.fromWkt("Polygon ((0 0, 10 0, 10 10, 0 10, 0 0))")
        assert polygon_parts(geom).asWkt(0) == "MultiPolygon (((0 0, 10 0, 10 10, 0 10, 0 0)))"
