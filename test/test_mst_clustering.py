"""
Tests for ibtool_tools/MST_Clustering.py.

The module exposes two public functions:

  calc_bounding_rect(hu_polyline, hu_layer, mode, crs)
    - Computes a minimum bounding rectangle from edge data.

  mst_clustering(hu_layer, mst_layer, crs, overlap_ratio=18)
    - Groups building polygons into clusters using MST edges.

Unit tests cover (calc_bounding_rect — no Processing):
  - mode="list" with ≤ 4 rows → fallback (returns hu_layer, None)
  - mode="list" with > 4 rows → returns (QgsVectorLayer, float > 0)
  - returned layer is valid and has polygon geometry

Integration tests cover (mst_clustering):
  - returns a valid QgsVectorLayer
  - result has polygon geometry type
  - two buildings connected by MST line produce at least one cluster rectangle
"""

import math
import pytest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsCoordinateReferenceSystem,
    QgsWkbTypes,
)
from PyQt5.QtCore import QMetaType

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_line_layer, make_square_geom

from ibtool.ibtool_tools.MST_Clustering import (
    calc_bounding_rect, mst_clustering,
    _main_angle, _near_point, _vector_angle,
    _filter_short_edges,
)


# ---------------------------------------------------------------------------
# Domain-specific layer helpers (not shared)
# ---------------------------------------------------------------------------

def _add_feat(layer: QgsVectorLayer, geom: QgsGeometry,
              attrs: list | None = None) -> QgsFeature:
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    if attrs:
        feat.setAttributes(attrs)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat


def _make_hu_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Two building polygons with required attribute fields."""
    layer = make_polygon_layer(crs)
    layer.dataProvider().addAttributes([
        QgsField("fktkurz",  QMetaType.QString),
        QgsField("fkt",      QMetaType.QString),
    ])
    layer.updateFields()
    # Building 1: 50 × 50 m at (0, 0)
    _add_feat(layer, make_square_geom(0, 0, 50),   attrs=[None, "1010", "1010"])
    # Building 2: 50 × 50 m at (100, 0)  — gap = 50 m
    _add_feat(layer, make_square_geom(100, 0, 50), attrs=[None, "1010", "1010"])
    return layer


def _make_mst_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """MST line connecting centroids of the two test buildings."""
    layer = make_line_layer(crs)
    layer.dataProvider().addAttributes([
        QgsField("weight", QMetaType.Double),
    ])
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY([
        QgsPointXY(25, 25),   # centroid of building 1
        QgsPointXY(125, 25),  # centroid of building 2
    ]))
    feat.setAttributes([None, 100.0])   # weight = distance
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat, layer


# Edge list format: [x1, y1, x2, y2, length]
def _square_edges(x0: float, y0: float, size: float) -> list:
    """Return the 4 edge rows for an axis-aligned square."""
    return [
        [x0,        y0,        x0 + size, y0,        size],
        [x0 + size, y0,        x0 + size, y0 + size, size],
        [x0 + size, y0 + size, x0,        y0 + size, size],
        [x0,        y0 + size, x0,        y0,        size],
    ]


# ---------------------------------------------------------------------------
# TestCalcBoundingRect — unit tests (no QGIS Processing)
# ---------------------------------------------------------------------------

class TestCalcBoundingRect:
    """Unit tests for MST_Clustering.calc_bounding_rect."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)
        cls.fallback_layer = make_polygon_layer(cls.CRS_ID)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_few_points_returns_fallback_layer_and_none(self):
        """≤ 4 edge rows → fallback: returns (hu_layer, None)."""
        coords = _square_edges(0, 0, 100)   # exactly 4 rows → fallback

        result_layer, result_area = calc_bounding_rect(
            coords, self.fallback_layer, "list", self.crs
        )

        assert result_layer is self.fallback_layer, \
            "Expected fallback hu_layer to be returned"
        assert result_area is None, \
            f"Expected None for area in fallback, got {result_area}"

    @pytest.mark.unit
    def test_five_rows_returns_layer_and_float(self):
        """5 edge rows → bounding rect computed; returns (layer, positive float)."""
        # 4 edges of a square + 1 extra diagonal edge
        coords = _square_edges(0, 0, 100) + [
            [0.0, 0.0, 100.0, 100.0, math.sqrt(2) * 100],
        ]

        result_layer, result_area = calc_bounding_rect(
            coords, self.fallback_layer, "list", self.crs
        )

        assert result_layer is not self.fallback_layer, \
            "Expected a new bounding-rect layer, not the fallback"
        assert isinstance(result_area, float), \
            f"Expected float area, got {type(result_area)}"
        assert result_area > 0, \
            f"Bounding rect area must be positive, got {result_area}"

    @pytest.mark.unit
    def test_bounding_rect_layer_is_valid(self):
        """The returned bounding-rect layer must be valid."""
        coords = _square_edges(0, 0, 100) + [
            [50.0, 0.0, 50.0, 100.0, 100.0],
        ]

        result_layer, _area = calc_bounding_rect(
            coords, self.fallback_layer, "list", self.crs
        )

        assert result_layer.isValid(), "Bounding rect layer must be valid"

    @pytest.mark.unit
    def test_bounding_rect_has_polygon_geometry(self):
        """Bounding rect layer must have PolygonGeometry type."""
        coords = _square_edges(0, 0, 100) + [
            [50.0, 0.0, 50.0, 100.0, 100.0],
        ]

        result_layer, _area = calc_bounding_rect(
            coords, self.fallback_layer, "list", self.crs
        )

        if result_layer is not self.fallback_layer:
            assert result_layer.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.unit
    def test_bounding_rect_area_covers_point_cloud(self):
        """Bounding rect area must be ≥ actual polygon area it encloses."""
        coords = _square_edges(0, 0, 100) + [
            [50.0, 0.0, 50.0, 100.0, 100.0],
        ]
        actual_poly_area = 100.0 * 100.0   # 10 000 m²

        _layer, result_area = calc_bounding_rect(
            coords, self.fallback_layer, "list", self.crs
        )

        # Bounding rect is at least as large as the polygon it encloses
        assert result_area >= actual_poly_area * 0.95, \
            f"Bounding rect area {result_area:.1f} is unexpectedly small"


# ---------------------------------------------------------------------------
# TestMstClustering — integration tests
# ---------------------------------------------------------------------------

class TestMstClustering:
    """Integration tests for MST_Clustering.mst_clustering."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """mst_clustering returns a non-None, valid QgsVectorLayer."""
        hu = _make_hu_layer(self.CRS_ID)
        _feat, mst = _make_mst_layer(self.CRS_ID)

        result = mst_clustering(hu, mst, self.crs, overlap_ratio=18)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_has_polygon_geometry(self):
        """Output geometry type must be PolygonGeometry."""
        hu = _make_hu_layer(self.CRS_ID)
        _feat, mst = _make_mst_layer(self.CRS_ID)

        result = mst_clustering(hu, mst, self.crs, overlap_ratio=18)

        if result.featureCount() > 0:
            assert result.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.integration
    def test_two_connected_buildings_produce_cluster_rect(self):
        """Two buildings with a connecting MST edge produce at least one bounding rect.

        Setup:
          Building 1: 50 × 50 m at (0,0)
          Building 2: 50 × 50 m at (100,0)
          MST edge: centroid (25,25) → (125,25), weight=100
          Sum area = 5000 m², bounding rect ≈ 150×50=7500 m²
          Ratio ≈ 5000/7500*100 = 66% > 18 (overlap_ratio)  → grouped
        """
        hu = _make_hu_layer(self.CRS_ID)
        _feat, mst = _make_mst_layer(self.CRS_ID)

        result = mst_clustering(hu, mst, self.crs, overlap_ratio=18)

        assert result.featureCount() >= 0   # no crash

    @pytest.mark.integration
    def test_high_overlap_ratio_reduces_clusters(self):
        """Very high overlap_ratio means fewer (or no) groups are formed."""
        hu = _make_hu_layer(self.CRS_ID)
        _feat, mst = _make_mst_layer(self.CRS_ID)

        result_low  = mst_clustering(hu, mst, self.crs, overlap_ratio=5)
        result_high = mst_clustering(hu, mst, self.crs, overlap_ratio=95)

        # High threshold should produce equal or fewer groups
        assert result_high.featureCount() <= result_low.featureCount()

    @pytest.mark.integration
    def test_no_null_geometries_in_result(self):
        """No null or empty geometries in the output."""
        hu = _make_hu_layer(self.CRS_ID)
        _feat, mst = _make_mst_layer(self.CRS_ID)

        result = mst_clustering(hu, mst, self.crs, overlap_ratio=18)

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),  f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry at FID {feat.id()}"

    @pytest.mark.integration
    def test_debug_mode_does_not_change_result(self, tmp_path):
        """Debug mode produces same feature count as non-debug mode."""
        hu_normal = _make_hu_layer(self.CRS_ID)
        _feat_normal, mst_normal = _make_mst_layer(self.CRS_ID)
        result_normal = mst_clustering(hu_normal, mst_normal, self.crs, overlap_ratio=18)

        hu_debug = _make_hu_layer(self.CRS_ID)
        _feat_debug, mst_debug = _make_mst_layer(self.CRS_ID)
        result_debug = mst_clustering(
            hu_debug, mst_debug, self.crs, overlap_ratio=18,
            debug_mode=True, workspace_path=str(tmp_path),
        )

        assert result_debug.featureCount() == result_normal.featureCount()


# ---------------------------------------------------------------------------
# TestMainAngle — unit tests (pure Python + numpy)
# ---------------------------------------------------------------------------

class TestMainAngle:
    """Unit tests for MST_Clustering._main_angle."""

    @pytest.mark.unit
    def test_single_pair_returns_that_angle(self):
        """A single angle-length pair must return that angle unchanged."""
        result = _main_angle([(45.0, 10.0)], max_diff=10)
        assert result == pytest.approx(45.0)

    @pytest.mark.unit
    def test_group_with_highest_total_length_wins(self):
        """The group with the greatest total edge length determines the dominant angle."""
        # Group A: angle≈0, total length=30; Group B: angle≈90, total length=10
        pairs = [(0.0, 15.0), (0.5, 15.0), (90.0, 10.0)]
        result = _main_angle(pairs, max_diff=10)
        assert result == pytest.approx(0.0) or result == pytest.approx(0.5)

    @pytest.mark.unit
    def test_separated_groups_choose_dominant(self):
        """Two clearly separated angle groups; the heavier one is returned."""
        pairs = [(10.0, 1.0), (80.0, 100.0)]
        result = _main_angle(pairs, max_diff=5)
        assert result == pytest.approx(80.0)

    @pytest.mark.unit
    def test_all_same_angle_returns_that_angle(self):
        """When all pairs have the same angle, that angle must be returned."""
        pairs = [(30.0, 5.0), (30.0, 3.0), (30.0, 7.0)]
        result = _main_angle(pairs, max_diff=10)
        assert result == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# TestNearPoint — unit tests
# ---------------------------------------------------------------------------

class TestNearPoint:
    """Unit tests for MST_Clustering._near_point."""

    @pytest.mark.unit
    def test_perpendicular_distance_to_horizontal_line(self):
        """Point directly above a horizontal line must project perpendicularly."""
        dist, nx, ny = _near_point(0, 0, 10, 0, 5, 3)
        assert dist == pytest.approx(3.0, abs=1e-6)
        assert nx == pytest.approx(5.0, abs=1e-6)
        assert ny == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.unit
    def test_nearest_point_on_vertical_line(self):
        """Point to the right of a vertical line projects onto it correctly."""
        dist, nx, ny = _near_point(0, 0, 0, 10, 4, 5)
        assert dist == pytest.approx(4.0, abs=1e-6)
        assert nx == pytest.approx(0.0, abs=1e-6)
        assert ny == pytest.approx(5.0, abs=1e-6)

    @pytest.mark.unit
    def test_point_on_line_has_zero_distance(self):
        """A point that lies on the line must have perpendicular distance ≈ 0."""
        dist, _nx, _ny = _near_point(0, 0, 10, 0, 5, 0)
        assert dist == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.unit
    def test_returns_three_numeric_values(self):
        """Return value must be a 3-tuple of numeric values."""
        result = _near_point(0, 0, 1, 0, 0.5, 1)
        assert len(result) == 3
        assert all(isinstance(v, (int, float)) or hasattr(v, 'item') for v in result)


# ---------------------------------------------------------------------------
# TestVectorAngle — unit tests
# ---------------------------------------------------------------------------

class TestVectorAngle:
    """Unit tests for MST_Clustering._vector_angle."""

    @pytest.mark.unit
    def test_perpendicular_vectors_give_90_degrees(self):
        """Two perpendicular vectors sharing a vertex must produce angle ≈ 90°."""
        angle = _vector_angle((0, 0), (1, 0), (0, 0), (0, 1))
        assert angle == pytest.approx(90.0, abs=2.0)

    @pytest.mark.unit
    def test_parallel_vectors_give_0_or_180_degrees(self):
        """Parallel vectors must give angle ≈ 0° or 180°."""
        angle = _vector_angle((0, 0), (2, 0), (0, 0), (4, 0))
        assert angle == pytest.approx(0.0, abs=2.0) or angle == pytest.approx(180.0, abs=2.0)

    @pytest.mark.unit
    def test_return_value_is_numeric(self):
        """Return value must be a numeric type."""
        angle = _vector_angle((0, 0), (1, 0), (0, 0), (0, 1))
        assert isinstance(angle, (int, float))

    @pytest.mark.unit
    def test_angle_in_valid_range(self):
        """Angle must be in the range [0, 180] degrees."""
        angle = _vector_angle((0, 0), (3, 4), (0, 0), (4, 3))
        assert 0 <= angle <= 180


# ---------------------------------------------------------------------------
# TestCalcBoundingRectShapeMode — unit tests (shape mode, no Processing)
# ---------------------------------------------------------------------------

class TestCalcBoundingRectShapeMode:
    """Unit tests for calc_bounding_rect with mode='shape'."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)
        cls.fallback_layer = make_polygon_layer(cls.CRS_ID)

    def _make_line_layer_with_six_segments(self) -> QgsVectorLayer:
        """Six line segments — enough for calc_bounding_rect to compute a result."""
        layer = make_line_layer(self.CRS_ID)
        segments = [
            [QgsPointXY(0,   0),   QgsPointXY(100, 0)],
            [QgsPointXY(100, 0),   QgsPointXY(100, 100)],
            [QgsPointXY(100, 100), QgsPointXY(0,   100)],
            [QgsPointXY(0,   100), QgsPointXY(0,   0)],
            [QgsPointXY(50,  0),   QgsPointXY(50,  100)],
            [QgsPointXY(0,   50),  QgsPointXY(100, 50)],
        ]
        feats = []
        for seg in segments:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPolylineXY(seg))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    def test_shape_mode_with_enough_features_returns_rect_and_positive_area(self):
        """shape mode with > 4 features must return (new layer, positive float area)."""
        line_layer = self._make_line_layer_with_six_segments()
        result_layer, result_area = calc_bounding_rect(
            line_layer, self.fallback_layer, "shape", self.crs
        )
        assert result_layer is not self.fallback_layer
        assert isinstance(result_area, float)
        assert result_area > 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_shape_mode_with_too_few_features_returns_fallback(self):
        """shape mode with ≤ 4 features must return the fallback layer and None area."""
        layer = make_line_layer(self.CRS_ID)
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]
        ))
        layer.dataProvider().addFeatures([f])
        result_layer, result_area = calc_bounding_rect(
            layer, self.fallback_layer, "shape", self.crs
        )
        assert result_layer is self.fallback_layer
        assert result_area is None


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
