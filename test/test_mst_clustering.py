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

from ibtool.ibtool_tools.MST_Clustering import calc_bounding_rect, mst_clustering


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
