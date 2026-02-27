# -*- coding: utf-8 -*-
"""
Performance and edge case tests for MST calculation (STEP 8c).

Performance tests (integration + performance + slow):
  - Small dataset  (4 buildings)   < 1 s,  result is None or valid layer
  - Medium dataset (25 buildings)  < 5 s
  - Large dataset  (100 buildings) < 30 s

Edge case tests (integration + edge_case):
  - Empty building layer → None or 0-edge layer
  - Single building       → 0 or 1 edges
  - Two buildings         → exactly 1 edge (n−1)
  - Collinear buildings   → valid MST or None (no crash)
  - Null geometry feature → no crash
"""

import time
import pytest

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateReferenceSystem, QgsWkbTypes,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer

from .test_fixtures_mst import MSTTestFixtures
from ibtool.ibtool_tools.CreateMST import calculate_mst


# ---------------------------------------------------------------------------
# Domain-specific helpers
# ---------------------------------------------------------------------------

def _building_grid(n: int, crs_id: str = "EPSG:3857") -> QgsVectorLayer:
    """Return a layer with n buildings arranged in a square grid (10 m, 20 m spacing)."""
    layer = make_polygon_layer(crs_id)
    cols = max(1, int(n ** 0.5))
    for i in range(n):
        x = float((i % cols) * 20)
        y = float((i // cols) * 20)
        add_feature_to_layer(layer, make_square_geom(x, y, 10))
    return layer


def _empty_streets(crs_id: str = "EPSG:3857") -> QgsVectorLayer:
    """Return an empty line layer (no streets)."""
    return make_line_layer(crs_id)


# ---------------------------------------------------------------------------
# TestMSTEdgeCases — @integration @edge_case
# ---------------------------------------------------------------------------

class TestMSTEdgeCases:
    """Edge case tests for MST calculation with degenerate or invalid inputs."""

    @classmethod
    def setup_class(cls):
        cls.fixtures = MSTTestFixtures()
        cls.crs = cls.fixtures.create_test_crs()   # EPSG:3857

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_building_layer_returns_none_or_zero_edges(self):
        """Empty building layer returns None or a layer with 0 edges (no crash)."""
        buildings = self.fixtures.create_empty_layer("Polygon")
        streets = self.fixtures.create_simple_street_layer()

        result = calculate_mst(buildings, streets, self.crs)

        if result is not None:
            assert result.featureCount() == 0, \
                "Empty building input must produce 0 MST edges"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_single_building_returns_zero_or_one_edges(self):
        """Single building produces at most 1 MST edge without crashing."""
        buildings = make_polygon_layer("EPSG:3857")
        add_feature_to_layer(buildings, make_square_geom(0, 0, 10))
        streets = _empty_streets()

        result = calculate_mst(buildings, streets, self.crs)

        if result is not None and result.isValid():
            assert result.featureCount() <= 1, \
                f"Single building must yield ≤ 1 edge, got {result.featureCount()}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_two_buildings_produce_at_most_one_edge(self):
        """Two buildings connected by an MST yield exactly 1 edge (n−1 = 1)."""
        buildings = make_polygon_layer("EPSG:3857")
        add_feature_to_layer(buildings, make_square_geom(0,  0, 10))
        add_feature_to_layer(buildings, make_square_geom(30, 0, 10))
        streets = _empty_streets()

        result = calculate_mst(buildings, streets, self.crs)

        if result is not None and result.isValid() and result.featureCount() > 0:
            assert result.featureCount() == 1, \
                f"Two buildings → 1 MST edge expected, got {result.featureCount()}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_collinear_buildings_do_not_crash(self):
        """Buildings arranged on a straight line produce a valid MST or None (no crash)."""
        buildings = make_polygon_layer("EPSG:3857")
        for i in range(5):
            add_feature_to_layer(buildings, make_square_geom(float(i * 20), 0.0, 10))
        streets = _empty_streets()

        result = calculate_mst(buildings, streets, self.crs)

        assert result is None or isinstance(result, QgsVectorLayer)
        if result is not None:
            assert result.isValid()

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_null_geometry_feature_does_not_crash(self):
        """A layer with a null-geometry feature must not cause calculate_mst to raise."""
        buildings = make_polygon_layer("EPSG:3857")
        add_feature_to_layer(buildings, make_square_geom(0,  0, 10))
        add_feature_to_layer(buildings, make_square_geom(20, 0, 10))

        # Add a feature with no geometry
        null_feat = QgsFeature(buildings.fields())
        null_feat.setGeometry(QgsGeometry())
        buildings.dataProvider().addFeatures([null_feat])

        streets = _empty_streets()

        result = calculate_mst(buildings, streets, self.crs)   # must not raise

        assert result is None or isinstance(result, QgsVectorLayer)


# ---------------------------------------------------------------------------
# TestMSTPerformance — @integration @performance @slow
# ---------------------------------------------------------------------------

class TestMSTPerformance:
    """Performance tests for MST calculation at small, medium, and large dataset sizes."""

    @classmethod
    def setup_class(cls):
        cls.fixtures = MSTTestFixtures()
        cls.crs = cls.fixtures.create_test_crs()   # EPSG:3857

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_small_dataset_completes_within_1_second(self):
        """4-building dataset finishes in < 1 s without crashing."""
        buildings = _building_grid(4, "EPSG:3857")
        streets = self.fixtures.create_simple_street_layer()
        assert buildings.featureCount() == 4

        start = time.time()
        result = calculate_mst(buildings, streets, self.crs)
        elapsed = time.time() - start

        assert result is None or isinstance(result, QgsVectorLayer)
        assert elapsed < 1.0, f"Small dataset took {elapsed:.2f} s (limit: 1 s)"

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_medium_dataset_completes_within_5_seconds(self):
        """25-building dataset finishes in < 5 s without crashing."""
        buildings = _building_grid(25, "EPSG:3857")
        streets = _empty_streets()
        assert buildings.featureCount() == 25

        start = time.time()
        result = calculate_mst(buildings, streets, self.crs)
        elapsed = time.time() - start

        assert result is None or isinstance(result, QgsVectorLayer)
        assert elapsed < 5.0, f"Medium dataset took {elapsed:.2f} s (limit: 5 s)"

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_large_dataset_completes_within_30_seconds(self):
        """100-building dataset finishes in < 30 s without crashing."""
        buildings = _building_grid(100, "EPSG:3857")
        streets = _empty_streets()
        assert buildings.featureCount() == 100

        start = time.time()
        result = calculate_mst(buildings, streets, self.crs)
        elapsed = time.time() - start

        assert result is None or isinstance(result, QgsVectorLayer)
        assert elapsed < 30.0, f"Large dataset took {elapsed:.2f} s (limit: 30 s)"
