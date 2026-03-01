# -*- coding: utf-8 -*-
"""Tests for helpers/edge_catch_utils.py.

Focuses on functions that can be tested without triggering QGIS Processing
algorithms:
  - _normalize_node          (pure Python + QgsPointXY)
  - apply_filter_rules       (pure Python — no QGIS at all)
  - build_catch_polygon      (QgsPointXY + QgsGeometry, no processing.run)
  - project_point_to_line    (QgsPointXY + QgsGeometry)

Higher-level functions (create_shortest_lines_to_roads, filter_roads_near_buildings,
process_single_feature) depend on many processing.run calls and are marked as
integration tests; they are left for dedicated integration tests against real data.
"""
import math
import pytest

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from .utilities import get_qgis_app
from ibtool.helpers.edge_catch_utils import (
    _normalize_node,
    apply_filter_rules,
    build_catch_polygon,
    project_point_to_line,
    create_shortest_lines_to_roads,
    _apply_rule_parallel_close_endpoints,
    _apply_rule_all_parallel,
    _apply_rule_angle_outliers,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _line(distance: float, angle: float, x1=0.0, y1=0.0, x2=10.0, y2=0.0) -> dict:
    """Minimal line_data dict for apply_filter_rules."""
    return {
        "distance": distance,
        "angle": angle,
        "x1": x1, "y1": y1,
        "x2": x2, "y2": y2,
        "feature": None,
    }


# ── _normalize_node ───────────────────────────────────────────────────────────

class TestNormalizeNode:
    """Tests for _normalize_node."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_hashable_tuple(self):
        pt = QgsPointXY(3.14159, 2.71828)
        key = _normalize_node(pt)
        assert isinstance(key, tuple)
        assert len(key) == 2
        # Must be usable as a dict key (hashable)
        d = {key: "ok"}
        assert d[key] == "ok"

    @pytest.mark.unit
    def test_rounds_to_8_decimal_places(self):
        pt = QgsPointXY(1.123456789, 9.987654321)
        key = _normalize_node(pt)
        assert key[0] == round(1.123456789, 8)
        assert key[1] == round(9.987654321, 8)

    @pytest.mark.unit
    def test_same_point_produces_same_key(self):
        pt1 = QgsPointXY(10.0, 20.0)
        pt2 = QgsPointXY(10.0, 20.0)
        assert _normalize_node(pt1) == _normalize_node(pt2)

    @pytest.mark.unit
    def test_different_points_produce_different_keys(self):
        pt1 = QgsPointXY(0.0, 0.0)
        pt2 = QgsPointXY(1.0, 0.0)
        assert _normalize_node(pt1) != _normalize_node(pt2)


# ── apply_filter_rules ────────────────────────────────────────────────────────

class TestApplyFilterRules:
    """Tests for apply_filter_rules.

    All inputs are plain dicts — no QGIS objects required.
    """

    @pytest.mark.unit
    def test_empty_input_returns_empty(self):
        assert apply_filter_rules([], min_lines_to_keep=2) == []

    @pytest.mark.unit
    def test_all_beyond_max_dist_returns_empty(self):
        """Lines with distance >= 70 (MAX_DIST) are all removed → empty result."""
        lines = [_line(80, 45), _line(100, 90), _line(75, 135)]
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        assert result == []

    @pytest.mark.unit
    def test_rule1_removes_lines_beyond_max_dist(self):
        """Lines with distance >= 70 are removed by Rule 1."""
        lines = [
            _line(30, 45),   # kept
            _line(80, 135),  # removed (>= 70)
            _line(20, 225),  # kept
        ]
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        distances = [r["distance"] for r in result]
        assert 80 not in distances

    @pytest.mark.unit
    def test_minimum_lines_respected_after_rule1(self):
        """After Rule 1, if only min_lines_to_keep lines remain, no further filtering."""
        lines = [
            _line(30, 45),
            _line(25, 90),
            _line(80, 135),  # removed by Rule 1
        ]
        # After Rule 1: 2 lines remain == min_lines_to_keep → return early
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        assert len(result) == 2

    @pytest.mark.unit
    def test_rule3b_all_four_parallel_returns_two_shortest(self):
        """Rule 3b: 4 lines with nearly identical angles → keep the 2 shortest."""
        lines = [
            _line(40, 90.0, x2=0, y2=40),
            _line(35, 91.0, x1=5, x2=5, y2=35),
            _line(25, 89.0, x1=10, x2=10, y2=25),
            _line(20, 90.5, x1=15, x2=15, y2=20),
        ]
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        assert len(result) == 2
        distances = sorted(r["distance"] for r in result)
        assert distances == [20, 25]

    @pytest.mark.unit
    def test_result_never_fewer_than_min_lines_to_keep(self):
        """The result must always contain at least min_lines_to_keep lines (if input allows)."""
        lines = [_line(d, float(i * 20)) for i, d in enumerate([10, 20, 30, 40])]
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        assert len(result) >= 2

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_single_line_below_max_dist(self):
        """One line that passes Rule 1 but is < min_lines_to_keep → still returned."""
        result = apply_filter_rules([_line(10, 45)], min_lines_to_keep=2)
        assert len(result) == 1

    @pytest.mark.unit
    def test_rule3a_removes_longer_of_two_parallel_with_close_endpoints(self):
        """Rule 3a: two parallel lines with nearly equal endpoints → longer one removed."""
        # Two parallel lines (angle diff = 0.5° < ANGLE_THRESHOLD=2°) with close endpoints
        parallel_1 = _line(40, 45.0, x1=0, y1=0, x2=28.0, y2=28.0)
        parallel_2 = _line(35, 45.5, x1=5, y1=5, x2=29.7, y2=29.7)
        # Two orthogonal lines to ensure we have > min_lines_to_keep after Rule 1
        ortho_1 = _line(30, 315.0, x1=0, y1=0, x2=21.2, y2=-21.2)
        ortho_2 = _line(25, 135.0, x1=0, y1=0, x2=-17.7, y2=17.7)

        lines = [parallel_1, parallel_2, ortho_1, ortho_2]
        result = apply_filter_rules(lines, min_lines_to_keep=2)
        distances = [r["distance"] for r in result]
        # The longer parallel line (dist=40) should be removed
        assert 40 not in distances
        assert 35 in distances


# ── build_catch_polygon ───────────────────────────────────────────────────────

class TestBuildCatchPolygon:
    """Tests for build_catch_polygon."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_returns_valid_polygon_for_four_distinct_points(self):
        """Four distinct corner points must produce a non-null, valid polygon."""
        edge_start = QgsPointXY(0, 0)
        edge_end   = QgsPointXY(10, 0)
        foot_b     = QgsPointXY(10, -20)
        foot_a     = QgsPointXY(0, -20)
        poly = build_catch_polygon(edge_start, edge_end, foot_a, foot_b)
        assert poly is not None
        assert not poly.isNull()
        assert not poly.isEmpty()

    @pytest.mark.unit
    def test_polygon_has_correct_geometry_type(self):
        edge_start = QgsPointXY(0, 0)
        edge_end   = QgsPointXY(10, 0)
        foot_b     = QgsPointXY(10, -20)
        foot_a     = QgsPointXY(0, -20)
        poly = build_catch_polygon(edge_start, edge_end, foot_a, foot_b)
        assert poly is not None
        assert poly.type() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.unit
    def test_with_intermediate_road_vertices(self):
        """Including road intermediate vertices must still produce a valid polygon."""
        edge_start = QgsPointXY(0, 0)
        edge_end   = QgsPointXY(10, 0)
        foot_a     = QgsPointXY(0, -20)
        foot_b     = QgsPointXY(10, -20)
        intermediates = [QgsPointXY(3, -22), QgsPointXY(7, -22)]
        poly = build_catch_polygon(edge_start, edge_end, foot_a, foot_b, intermediates)
        assert poly is not None
        assert not poly.isNull()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_when_fewer_than_four_points(self):
        """Degenerate input (all same point) must not produce a valid Polygon."""
        # edge_start == edge_end == foot_a == foot_b → polygon collapses.
        # makeValid() may convert this to a Point geometry, which is acceptable.
        same = QgsPointXY(5, 5)
        result = build_catch_polygon(same, same, same, same)
        # Either None, or a non-Polygon geometry (e.g. Point after makeValid), is acceptable.
        if result is not None and not result.isNull() and not result.isEmpty():
            assert result.type() != QgsWkbTypes.PolygonGeometry, (
                "Degenerate input should not produce a valid Polygon geometry"
            )


# ── project_point_to_line ─────────────────────────────────────────────────────

class TestProjectPointToLine:
    """Tests for project_point_to_line."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_projects_point_onto_horizontal_line(self):
        """A point above a horizontal line must project to the line itself."""
        line_geom = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(100, 0)]
        )
        point = QgsPointXY(50, 30)
        projected, dist = project_point_to_line(point, line_geom)
        assert projected is not None
        assert projected.x() == pytest.approx(50.0, abs=1e-3)
        assert projected.y() == pytest.approx(0.0, abs=1e-3)
        assert dist == pytest.approx(30.0, abs=1e-3)

    @pytest.mark.unit
    def test_distance_is_non_negative(self):
        line_geom = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(100, 0)]
        )
        projected, dist = project_point_to_line(QgsPointXY(50, 10), line_geom)
        assert dist >= 0

    @pytest.mark.unit
    def test_point_on_line_has_zero_distance(self):
        """A point that already lies on the line must have distance ≈ 0."""
        line_geom = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(100, 0)]
        )
        projected, dist = project_point_to_line(QgsPointXY(50, 0), line_geom)
        assert dist == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_line_returns_none_and_inf(self):
        """A null/empty line geometry must return (None, inf) without crashing."""
        null_geom = QgsGeometry()
        projected, dist = project_point_to_line(QgsPointXY(5, 5), null_geom)
        assert projected is None
        assert dist == float("inf")


# ── create_shortest_lines_to_roads (basic validation) ────────────────────────

class TestCreateShortestLinesToRoads:
    """Basic validation tests for create_shortest_lines_to_roads.

    These tests cover input-validation paths (None / invalid / wrong geometry
    type) that execute no processing.run calls.
    """

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_point_layer(self) -> QgsVectorLayer:
        layer = QgsVectorLayer("Point?crs=EPSG:25833", "pts", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
        layer.dataProvider().addFeatures([f])
        return layer

    def _make_line_layer(self) -> QgsVectorLayer:
        layer = QgsVectorLayer("LineString?crs=EPSG:25833", "lines", "memory")
        f = QgsFeature()
        f.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(100, 0)])
        )
        layer.dataProvider().addFeatures([f])
        return layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_when_point_layer_is_none(self):
        result = create_shortest_lines_to_roads(None, self._make_line_layer())
        assert result is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_when_line_layer_is_none(self):
        result = create_shortest_lines_to_roads(self._make_point_layer(), None)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_none_when_point_layer_has_wrong_geometry(self):
        """Passing a polygon layer where a point layer is expected must return None."""
        polygon_layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "polys", "memory")
        f = QgsFeature()
        f.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0), QgsPointXY(10, 0),
                    QgsPointXY(10, 10), QgsPointXY(0, 10),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        polygon_layer.dataProvider().addFeatures([f])
        result = create_shortest_lines_to_roads(polygon_layer, self._make_line_layer())
        assert result is None

    @pytest.mark.unit
    def test_returns_layer_for_valid_inputs(self):
        """Valid point+line inputs must return a (possibly empty) QgsVectorLayer."""
        result = create_shortest_lines_to_roads(
            self._make_point_layer(), self._make_line_layer()
        )
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_point_with_null_geometry_does_not_crash(self):
        """A point layer where one feature has a null geometry must not crash."""
        layer = QgsVectorLayer("Point?crs=EPSG:25833", "pts_null", "memory")
        f = QgsFeature()
        # No geometry set → null geometry
        layer.dataProvider().addFeatures([f])
        result = create_shortest_lines_to_roads(layer, self._make_line_layer())
        assert result is not None
        assert isinstance(result, QgsVectorLayer)


# ── _apply_rule_parallel_close_endpoints ────────────────────────────────────

class TestApplyRuleParallelCloseEndpoints:
    """Direct unit tests for _apply_rule_parallel_close_endpoints."""

    @pytest.mark.unit
    def test_non_parallel_lines_are_unchanged(self):
        """Lines with very different angles must not be removed by Rule 3a."""
        lines = [
            _line(30, 0.0,   x1=0, y1=0, x2=30, y2=0),
            _line(25, 90.0,  x1=0, y1=0, x2=0,  y2=25),
        ]
        result = _apply_rule_parallel_close_endpoints(lines, min_lines_to_keep=2)
        assert len(result) == 2

    @pytest.mark.unit
    def test_parallel_with_close_endpoints_removes_longer(self):
        """Two parallel lines with endpoints within 5 m → remove the longer one."""
        # Same angle (0°), endpoints very close (< 5 m apart), different lengths
        short_line = _line(20, 0.0, x1=0, y1=0, x2=20.0, y2=0)
        long_line  = _line(40, 0.0, x1=5, y1=0, x2=22.0, y2=0)  # endpoint at x2=22 vs 20 → diff=2 < 5
        other_line = _line(30, 90.0, x1=0, y1=0, x2=0,  y2=30)

        lines = [short_line, long_line, other_line]
        result = _apply_rule_parallel_close_endpoints(lines, min_lines_to_keep=2)
        distances = [r["distance"] for r in result]
        assert 40 not in distances, "Longer parallel line should be removed"
        assert 20 in distances,    "Shorter parallel line should be kept"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_removal_prevented_when_below_min_lines_to_keep(self):
        """Rule 3a must not remove lines if the result would drop below min_lines_to_keep."""
        # Two parallel lines with close endpoints → would be removed → but min_lines=2
        short_line = _line(20, 0.0, x1=0, y1=0, x2=20, y2=0)
        long_line  = _line(40, 0.0, x1=0, y1=0, x2=20, y2=0)  # same endpoints
        lines = [short_line, long_line]
        result = _apply_rule_parallel_close_endpoints(lines, min_lines_to_keep=2)
        assert len(result) == 2  # no removal because it would go below 2


# ── _apply_rule_all_parallel ─────────────────────────────────────────────────

class TestApplyRuleAllParallel:
    """Direct unit tests for _apply_rule_all_parallel."""

    @pytest.mark.unit
    def test_returns_none_when_fewer_than_four_lines(self):
        """Rule 3b only applies to exactly 4 lines; < 4 must return None."""
        lines = [_line(10, 90.0), _line(20, 90.5), _line(15, 91.0)]
        result = _apply_rule_all_parallel(lines)
        assert result is None

    @pytest.mark.unit
    def test_returns_none_when_more_than_four_lines(self):
        """Rule 3b only applies to exactly 4 lines; > 4 must return None."""
        lines = [_line(10, 90.0)] * 5
        result = _apply_rule_all_parallel(lines)
        assert result is None

    @pytest.mark.unit
    def test_four_parallel_lines_returns_two_shortest(self):
        """Exactly 4 near-parallel lines must return the 2 with smallest distances."""
        lines = [
            _line(40, 90.0),
            _line(35, 91.0),
            _line(20, 89.5),
            _line(25, 90.5),
        ]
        result = _apply_rule_all_parallel(lines)
        assert result is not None
        assert len(result) == 2
        distances = sorted(r["distance"] for r in result)
        assert distances == [20, 25]

    @pytest.mark.unit
    def test_four_non_parallel_lines_returns_none(self):
        """Four lines with spread > _ALL_PARALLEL_THRESHOLD must return None."""
        lines = [
            _line(10, 0.0),
            _line(10, 90.0),
            _line(10, 45.0),
            _line(10, 135.0),
        ]
        result = _apply_rule_all_parallel(lines)
        assert result is None


# ── _apply_rule_angle_outliers ───────────────────────────────────────────────

class TestApplyRuleAngleOutliers:
    """Direct unit tests for _apply_rule_angle_outliers."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_two_or_fewer_lines_returned_unchanged(self):
        """Rule 4 skips processing when ≤ 2 lines are given."""
        lines = [_line(10, 45), _line(20, 90)]
        result = _apply_rule_angle_outliers(lines, min_lines_to_keep=2)
        assert result == lines

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_single_angle_group_returned_unchanged(self):
        """If all lines have similar angles (1 group), no group can be removed."""
        lines = [_line(10, 45.0), _line(20, 45.5), _line(30, 45.8)]
        result = _apply_rule_angle_outliers(lines, min_lines_to_keep=2)
        assert len(result) == 3

    @pytest.mark.unit
    def test_outlier_group_is_removed_when_far_enough(self):
        """Group with avg_dist > 2× second-largest avg_dist must be removed."""
        # Group A: angle≈0, avg_dist=10
        # Group B: angle≈90, avg_dist=5
        # Group C: angle≈45, avg_dist=100 → outlier (100 > 2×10)
        lines = [
            _line(10, 0.0),
            _line(10, 0.5),
            _line(5, 90.0),
            _line(5, 90.5),
            _line(100, 45.0),  # outlier group
        ]
        result = _apply_rule_angle_outliers(lines, min_lines_to_keep=2)
        outlier_distances = [r["distance"] for r in result if r["angle"] == 45.0]
        assert outlier_distances == [], "Outlier group (angle≈45, dist=100) should be removed"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_outlier_not_removed_when_fewer_than_three_groups(self):
        """Rule 4 requires at least 3 angle groups; with only 2 it must not remove."""
        lines = [
            _line(10, 0.0),
            _line(5, 90.0),
            _line(100, 90.5),
        ]
        # Only 2 angle groups (0° and 90°) → rule 4 does not apply
        result = _apply_rule_angle_outliers(lines, min_lines_to_keep=2)
        assert len(result) == 3
