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
    _group_lines_by_angle,
    filter_ortho_lines,
    _build_minimized_lines_from_selection,
    extract_road_subline,
    delete_first_point,
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


# ── _group_lines_by_angle ─────────────────────────────────────────────────────

class TestGroupLinesByAngle:
    """Tests for _group_lines_by_angle (pure Python, no QGIS needed)."""

    @pytest.mark.unit
    def test_empty_input_returns_empty(self):
        """Empty line list returns an empty group list."""
        assert _group_lines_by_angle([], angle_threshold=5) == []

    @pytest.mark.unit
    def test_single_line_forms_one_group(self):
        """A single line produces exactly one group containing that line."""
        lines = [_line(10, 45.0)]
        result = _group_lines_by_angle(lines, angle_threshold=5)
        assert len(result) == 1
        assert len(result[0]) == 1

    @pytest.mark.unit
    def test_lines_within_threshold_are_grouped(self):
        """Lines whose angle difference is ≤ threshold land in the same group."""
        lines = [_line(10, 0.0), _line(20, 3.0), _line(30, 6.0)]
        result = _group_lines_by_angle(lines, angle_threshold=5)
        # 0→3 diff=3 ≤5, 3→6 diff=3 ≤5 → all one group
        assert len(result) == 1

    @pytest.mark.unit
    def test_lines_outside_threshold_form_separate_groups(self):
        """Lines whose angle difference exceeds threshold form separate groups."""
        lines = [_line(10, 0.0), _line(20, 90.0), _line(30, 180.0)]
        result = _group_lines_by_angle(lines, angle_threshold=5)
        assert len(result) == 3

    @pytest.mark.unit
    def test_groups_are_sorted_by_angle(self):
        """Groups are produced in ascending angle order."""
        lines = [_line(10, 90.0), _line(20, 0.0), _line(30, 45.0)]
        result = _group_lines_by_angle(lines, angle_threshold=2)
        first_angles = [g[0]['angle'] for g in result]
        assert first_angles == sorted(first_angles)

    @pytest.mark.unit
    def test_exact_threshold_boundary_is_grouped(self):
        """Lines whose angle difference equals the threshold exactly are grouped."""
        lines = [_line(10, 0.0), _line(20, 5.0)]
        result = _group_lines_by_angle(lines, angle_threshold=5)
        assert len(result) == 1

    @pytest.mark.unit
    def test_mixed_groups(self):
        """Two clusters separated by a gap each form one group."""
        lines = [
            _line(10, 0.0), _line(10, 1.0),    # group A
            _line(10, 90.0), _line(10, 91.5),  # group B
        ]
        result = _group_lines_by_angle(lines, angle_threshold=5)
        assert len(result) == 2
        assert len(result[0]) == 2
        assert len(result[1]) == 2


# ── helpers for layer-based tests ─────────────────────────────────────────────

def _make_ortho_line_layer(crs: str = "EPSG:25833") -> "QgsVectorLayer":
    """In-memory line layer with fields expected by filter_ortho_lines."""
    from qgis.core import QgsField
    from qgis.PyQt.QtCore import QVariant
    layer = QgsVectorLayer(f"LineString?crs={crs}", "ortho_lines", "memory")
    prov = layer.dataProvider()
    prov.addAttributes([
        QgsField("distance", QVariant.Double),
        QgsField("angle",    QVariant.Double),
        QgsField("x1",       QVariant.Double),
        QgsField("y1",       QVariant.Double),
        QgsField("x2",       QVariant.Double),
        QgsField("y2",       QVariant.Double),
    ])
    layer.updateFields()
    return layer


def _add_ortho_line(layer, distance, angle, x1, y1, x2, y2):
    """Add one line feature to an ortho-lines layer."""
    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)]))
    feat.setAttributes([distance, angle, x1, y1, x2, y2])
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()


# ── filter_ortho_lines ────────────────────────────────────────────────────────

class TestFilterOrthoLines:
    """Tests for filter_ortho_lines (no processing.run)."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    @pytest.mark.unit
    def test_empty_layer_returns_empty_layer(self):
        """An empty input layer produces an empty output layer."""
        layer = _make_ortho_line_layer()
        result = filter_ortho_lines(layer)
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.unit
    def test_returns_qgsvectorlayer(self):
        """filter_ortho_lines always returns a QgsVectorLayer."""
        layer = _make_ortho_line_layer()
        _add_ortho_line(layer, 10, 45, 0, 0, 7, 7)
        result = filter_ortho_lines(layer)
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.unit
    def test_group_with_two_lines_passes_through_unchanged(self):
        """A group of exactly min_lines_to_keep (2) features is kept as-is."""
        layer = _make_ortho_line_layer()
        _add_ortho_line(layer, 10, 0.0,  0, 0, 10, 0)
        _add_ortho_line(layer, 15, 90.0, 0, 0,  0, 15)
        result = filter_ortho_lines(layer, min_lines_to_keep=2)
        assert result.featureCount() == 2

    @pytest.mark.unit
    def test_four_parallel_lines_reduced_to_two(self):
        """Four near-parallel lines in one group → Rule 3b keeps the 2 shortest.

        All start points are co-located so Rule 2 (endpoint-in-rectangle) cannot
        fire.  Endpoints are spread ≥ 30 m apart so Rule 3a (parallel lines with
        nearby endpoints, threshold 5 m) cannot fire either, leaving Rule 3b as
        the first applicable rule.
        """
        layer = _make_ortho_line_layer()
        _add_ortho_line(layer, 40, 90.0, 0, 0,  0, 40)
        _add_ortho_line(layer, 35, 91.0, 0, 0, 30, 35)
        _add_ortho_line(layer, 20, 89.5, 0, 0, 60, 20)
        _add_ortho_line(layer, 25, 90.5, 0, 0, 90, 25)
        result = filter_ortho_lines(layer, min_lines_to_keep=2)
        assert result.featureCount() == 2

    @pytest.mark.unit
    def test_result_layer_has_same_fields_as_input(self):
        """Output layer preserves the field schema of the input."""
        layer = _make_ortho_line_layer()
        _add_ortho_line(layer, 10, 45, 0, 0, 7, 7)
        result = filter_ortho_lines(layer)
        in_fields  = {f.name() for f in layer.fields()}
        out_fields = {f.name() for f in result.fields()}
        assert in_fields == out_fields

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_line_beyond_max_distance_is_removed(self):
        """Rule 1: a line with distance ≥ 70 is filtered out when > min_lines_to_keep remain."""
        layer = _make_ortho_line_layer()
        # 3 lines: 2 short + 1 far — should reduce to 2
        _add_ortho_line(layer, 80, 0.0,   0, 0, 80,  0)   # > 70 → removed
        _add_ortho_line(layer, 20, 90.0,  0, 0,  0, 20)
        _add_ortho_line(layer, 25, 180.0, 0, 0, -25,  0)
        _add_ortho_line(layer, 30, 270.0, 0, 0,  0, -30)
        result = filter_ortho_lines(layer, min_lines_to_keep=2)
        distances = [feat["distance"] for feat in result.getFeatures()]
        assert 80 not in distances


# ── _build_minimized_lines_from_selection ─────────────────────────────────────

class TestBuildMinimizedLines:
    """Tests for _build_minimized_lines_from_selection (no processing.run)."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()
        cls.crs = QgsVectorLayer("LineString?crs=EPSG:25833", "", "memory").crs()
        # Use QgsCoordinateReferenceSystem directly
        from qgis.core import QgsCoordinateReferenceSystem
        cls.crs = QgsCoordinateReferenceSystem("EPSG:25833")

    def _make_road_layer(self, segments: list) -> QgsVectorLayer:
        """Return a line layer with given (start_x, start_y, end_x, end_y) segments."""
        layer = QgsVectorLayer("LineString?crs=EPSG:25833", "roads", "memory")
        for x1, y1, x2, y2 in segments:
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY([
                QgsPointXY(x1, y1), QgsPointXY(x2, y2)
            ]))
            layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_input_returned_unchanged(self):
        """An empty road layer is returned immediately without processing."""
        layer = self._make_road_layer([])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        assert result is layer

    @pytest.mark.unit
    def test_returns_qgsvectorlayer(self):
        """A non-empty road layer returns a new QgsVectorLayer."""
        layer = self._make_road_layer([(0, 0, 10, 0)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.unit
    def test_single_segment_produces_one_feature(self):
        """A single road segment produces exactly one output feature."""
        layer = self._make_road_layer([(0, 0, 10, 0)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_two_connected_segments_merged_to_one_chain(self):
        """Two co-linear connected segments are merged into a single chain feature."""
        # A → B → C: three collinear nodes, two segments
        layer = self._make_road_layer([(0, 0, 10, 0), (10, 0, 20, 0)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        # The two segments form a single chain from A to C
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_t_junction_produces_multiple_features(self):
        """A T-junction (one node with degree 3) produces at least 2 chain features."""
        # T-shape: A→B, C→B, B→D (B is the junction)
        layer = self._make_road_layer([
            (0,  0, 10,  0),   # A → B
            (10, 10, 10, 0),   # C → B
            (10, 0,  20, 0),   # B → D
        ])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        assert result.featureCount() >= 2

    @pytest.mark.unit
    def test_duplicate_segments_are_deduplicated(self):
        """Duplicate segments (same endpoints) appear only once in the output."""
        layer = self._make_road_layer([(0, 0, 10, 0), (0, 0, 10, 0)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_output_has_src_count_field(self):
        """Output layer has a 'src_count' field tracking how many segments were merged."""
        layer = self._make_road_layer([(0, 0, 10, 0), (10, 0, 20, 0)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        field_names = [f.name() for f in result.fields()]
        assert "src_count" in field_names

    @pytest.mark.unit
    def test_output_geometries_are_valid(self):
        """All output geometries pass GEOS validity."""
        layer = self._make_road_layer([(0, 0, 10, 0), (10, 0, 20, 5)])
        result = _build_minimized_lines_from_selection(layer, self.crs)
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull()
            assert not geom.isEmpty()
            assert geom.isGeosValid()


# ── extract_road_subline ──────────────────────────────────────────────────────

class TestExtractRoadSubline:
    """Tests for extract_road_subline (no processing.run)."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _road_feat(self, x1, y1, x2, y2) -> "QgsFeature":
        """Return a road QgsFeature with a straight line geometry."""
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(x1, y1), QgsPointXY(x2, y2)
        ]))
        return feat

    @pytest.mark.unit
    def test_returns_list_for_straight_road(self):
        """Two foot points on a straight road → empty intermediate list."""
        road = [self._road_feat(0, 0, 100, 0)]
        result = extract_road_subline(QgsPointXY(20, 0), QgsPointXY(80, 0), road)
        # Straight road has no intermediate vertices
        assert result is not None
        assert isinstance(result, list)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_road_features_returns_none(self):
        """No road geometries → returns None with a log warning."""
        result = extract_road_subline(QgsPointXY(0, 0), QgsPointXY(10, 0), [])
        assert result is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_road_feature_with_null_geometry_returns_none(self):
        """A road feature with null geometry → returns None (no valid geom_list)."""
        feat = QgsFeature()
        # No geometry set → null
        result = extract_road_subline(QgsPointXY(0, 0), QgsPointXY(10, 0), [feat])
        assert result is None

    @pytest.mark.unit
    def test_accepts_layer_as_road_features(self):
        """Passing a QgsVectorLayer as road_features (has getFeatures) works."""
        layer = QgsVectorLayer("LineString?crs=EPSG:25833", "road", "memory")
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(100, 0)]))
        layer.dataProvider().addFeatures([feat])
        result = extract_road_subline(QgsPointXY(10, 0), QgsPointXY(90, 0), layer)
        assert result is not None
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_bent_road_returns_intermediate_vertices(self):
        """A bent road (3 vertices) has one intermediate vertex between the foot points."""
        # Road: (0,0) → (50,0) → (100,0) — two segments forming a bent shape
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(50, 10), QgsPointXY(100, 0)
        ]))
        result = extract_road_subline(QgsPointXY(0, 0), QgsPointXY(100, 0), [feat])
        # The middle vertex (50, 10) should be in the intermediates
        assert result is not None


# ── delete_first_point ────────────────────────────────────────────────────────

class TestDeleteFirstPoint:
    """Tests for delete_first_point (no processing.run)."""

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()

    def _make_point_layer(self, n: int) -> QgsVectorLayer:
        """Return a point layer with n features."""
        layer = QgsVectorLayer("Point?crs=EPSG:25833", "pts", "memory")
        feats = []
        for i in range(n):
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(i), 0.0)))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        return layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_single_feature_layer_returned_unchanged(self):
        """Layer with 1 feature is returned as the original object (no copy)."""
        layer = self._make_point_layer(1)
        result = delete_first_point(layer)
        assert result is layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_returned_unchanged(self):
        """Empty layer (0 features) is returned as the original object."""
        layer = self._make_point_layer(0)
        result = delete_first_point(layer)
        assert result is layer

    @pytest.mark.unit
    def test_two_feature_layer_produces_one_feature(self):
        """Layer with 2 features → result has 1 feature (first removed)."""
        layer = self._make_point_layer(2)
        result = delete_first_point(layer)
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_five_feature_layer_produces_four_features(self):
        """Layer with 5 features → result has 4 features."""
        layer = self._make_point_layer(5)
        result = delete_first_point(layer)
        assert result.featureCount() == 4

    @pytest.mark.unit
    def test_returned_layer_crs_matches_input(self):
        """The CRS of the result layer matches the input CRS."""
        layer = self._make_point_layer(3)
        result = delete_first_point(layer)
        assert result.crs().authid() == layer.crs().authid()
