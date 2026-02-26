"""
Tests for ibtool_tools/HoleClose.py.

Pipeline under test (hole_close):
  1. native:dissolve
  2. native:polygonstolines
  3. native:polygonize        → all enclosed areas (donut + hole polygons)
  4. get_hole_polygons()      → isolate hole polygons not within dissolved input
  5. shp_area2()              → compute Area field on holes
  6. native:extractbyattribute (Area <= max_hole_size)
  7. qgis:mergevectorlayers   → holes + dissolved input
  8. qgis:dissolve            → fill selected holes

Unit tests cover:
  - shp_area2  (no Processing, pure layer editing)
  - get_hole_polygons  (no Processing, pure Python iteration)

Integration tests cover:
  - hole_close with a small hole  → hole is filled
  - hole_close with a large hole  → hole is kept
  - hole_close with no holes      → area unchanged
  - result layer validity and geometry type
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

# QGIS must be initialised before any layer is created
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.ibtool_tools.HoleClose import hole_close
from ibtool.helpers.geometry_utils import get_hole_polygons, shp_area2


# ---------------------------------------------------------------------------
# Geometry / layer factory helpers
# ---------------------------------------------------------------------------

def _polygon_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Empty in-memory polygon layer."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", "test", "memory")
    layer.updateFields()
    return layer


def _square(x0: float, y0: float, size: float) -> QgsGeometry:
    """Axis-aligned square polygon."""
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x0,        y0),
        QgsPointXY(x0 + size, y0),
        QgsPointXY(x0 + size, y0 + size),
        QgsPointXY(x0,        y0 + size),
        QgsPointXY(x0,        y0),
    ]])


def _square_with_hole(
    outer: float,
    hx: float, hy: float, hole: float,
) -> QgsGeometry:
    """Outer square with a square hole cut out.

    Args:
        outer: Side length of the outer ring (starts at 0,0).
        hx, hy: Bottom-left corner of the hole.
        hole: Side length of the hole.
    """
    outer_ring = [
        QgsPointXY(0,     0),     QgsPointXY(outer, 0),
        QgsPointXY(outer, outer), QgsPointXY(0,     outer),
        QgsPointXY(0,     0),
    ]
    hole_ring = [
        QgsPointXY(hx,          hy),
        QgsPointXY(hx + hole,   hy),
        QgsPointXY(hx + hole,   hy + hole),
        QgsPointXY(hx,          hy + hole),
        QgsPointXY(hx,          hy),
    ]
    return QgsGeometry.fromPolygonXY([outer_ring, hole_ring])


def _add(layer: QgsVectorLayer, geom: QgsGeometry) -> QgsFeature:
    """Add one feature to a layer and return it."""
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat


def _total_area(layer: QgsVectorLayer) -> float:
    """Sum of geometry areas of all features in a layer."""
    return sum(
        f.geometry().area()
        for f in layer.getFeatures()
        if f.geometry() and not f.geometry().isNull() and not f.geometry().isEmpty()
    )


# ---------------------------------------------------------------------------
# TestShpArea2 — unit tests (no Processing algorithms)
# ---------------------------------------------------------------------------

class TestShpArea2:
    """Unit tests for helpers.geometry_utils.shp_area2."""

    def _layer_with_square(self, size: float = 100.0) -> QgsVectorLayer:
        layer = _polygon_layer()
        _add(layer, _square(0, 0, size))
        return layer

    @pytest.mark.unit
    def test_area_field_is_created_when_absent(self):
        """shp_area2 adds an 'Area' field when it does not yet exist."""
        layer = self._layer_with_square()
        assert layer.fields().indexFromName("Area") < 0
        shp_area2(layer)
        assert layer.fields().indexFromName("Area") >= 0

    @pytest.mark.unit
    def test_area_values_match_geometry_area(self):
        """Computed Area values equal QgsGeometry.area() for each feature."""
        layer = self._layer_with_square(100.0)
        shp_area2(layer)
        for feat in layer.getFeatures():
            expected = feat.geometry().area()
            assert abs(feat["Area"] - expected) < 1e-6, \
                f"Area mismatch: stored {feat['Area']}, expected {expected}"

    @pytest.mark.unit
    def test_returns_true_on_valid_layer(self):
        """shp_area2 returns True when it completes successfully."""
        layer = self._layer_with_square()
        result = shp_area2(layer)
        assert result is True

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_false_on_invalid_layer(self):
        """shp_area2 returns False for an invalid (uninitialised) layer."""
        invalid = QgsVectorLayer()
        result = shp_area2(invalid)
        assert result is False

    @pytest.mark.unit
    def test_existing_field_not_duplicated(self):
        """Calling shp_area2 twice does not add a second 'Area' field."""
        layer = self._layer_with_square()
        shp_area2(layer)
        field_count = layer.fields().count()
        shp_area2(layer)
        assert layer.fields().count() == field_count

    @pytest.mark.unit
    def test_custom_field_name_is_used(self):
        """A custom field name is added instead of 'Area'."""
        layer = self._layer_with_square()
        shp_area2(layer, field_name="Flaeche")
        assert layer.fields().indexFromName("Flaeche") >= 0
        assert layer.fields().indexFromName("Area") < 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer_returns_true_without_crash(self):
        """shp_area2 on a valid but empty layer must not crash."""
        layer = _polygon_layer()
        result = shp_area2(layer)
        assert result is True
        assert layer.fields().indexFromName("Area") >= 0

    @pytest.mark.unit
    def test_multiple_features_all_get_area(self):
        """All features in a multi-feature layer receive a non-zero area."""
        layer = _polygon_layer()
        for i in range(3):
            _add(layer, _square(float(i * 200), 0.0, 100.0))
        shp_area2(layer)
        for feat in layer.getFeatures():
            assert feat["Area"] is not None
            assert feat["Area"] > 0, f"Expected positive area, got {feat['Area']}"


# ---------------------------------------------------------------------------
# TestGetHolePolygons — unit tests (no Processing algorithms)
# ---------------------------------------------------------------------------

class TestGetHolePolygons:
    """Unit tests for helpers.geometry_utils.get_hole_polygons."""

    @pytest.mark.unit
    def test_result_is_valid_qgsvectorlayer(self):
        """get_hole_polygons always returns a valid QgsVectorLayer."""
        layer1 = _polygon_layer()
        _add(layer1, _square(0, 0, 10))
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))
        result = get_hole_polygons(layer1, layer2)
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.unit
    def test_polygon_inside_reference_is_not_a_hole(self):
        """A small polygon fully contained within the reference is NOT returned."""
        layer1 = _polygon_layer()
        _add(layer1, _square(10, 10, 20))   # 20×20 inside 100×100
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))    # 100×100 reference
        result = get_hole_polygons(layer1, layer2)
        assert result.featureCount() == 0

    @pytest.mark.unit
    def test_polygon_outside_reference_is_a_hole(self):
        """A polygon completely outside the reference IS returned as a hole."""
        layer1 = _polygon_layer()
        _add(layer1, _square(200, 200, 20))  # far outside reference
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))     # 100×100 reference
        result = get_hole_polygons(layer1, layer2)
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_mixed_features_only_outside_returned(self):
        """Only the feature outside the reference is returned, not the inner one."""
        layer1 = _polygon_layer()
        _add(layer1, _square(10, 10, 20))   # inside reference → not a hole
        _add(layer1, _square(200, 200, 20)) # outside reference → hole
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))
        result = get_hole_polygons(layer1, layer2)
        assert result.featureCount() == 1

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer1_returns_empty_layer(self):
        """If layer1 has no features, result is empty."""
        layer1 = _polygon_layer()          # empty
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))
        result = get_hole_polygons(layer1, layer2)
        assert result.featureCount() == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_layer2_returns_all_features(self):
        """When reference layer is empty, all features are holes (none are 'within')."""
        layer1 = _polygon_layer()
        _add(layer1, _square(0, 0, 50))
        _add(layer1, _square(100, 100, 50))
        layer2 = _polygon_layer()          # empty reference
        result = get_hole_polygons(layer1, layer2)
        assert result.featureCount() == 2

    @pytest.mark.unit
    def test_result_geometry_is_valid(self):
        """Geometries in the result layer are GEOS-valid."""
        layer1 = _polygon_layer()
        _add(layer1, _square(200, 200, 30))  # outside → will be returned
        layer2 = _polygon_layer()
        _add(layer2, _square(0, 0, 100))
        result = get_hole_polygons(layer1, layer2)
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull()
            assert not geom.isEmpty()
            assert geom.isGeosValid(), f"Invalid geometry: {geom.lastError()}"


# ---------------------------------------------------------------------------
# TestHoleClose — integration tests (uses QGIS Processing algorithms)
# ---------------------------------------------------------------------------

class TestHoleClose:
    """Integration tests for ibtool_tools.HoleClose.hole_close."""

    # -- Basic result validity -----------------------------------------------

    @pytest.mark.integration
    def test_result_is_valid_qgsvectorlayer(self):
        """hole_close returns a non-None, valid QgsVectorLayer."""
        layer = _polygon_layer()
        _add(layer, _square(0, 0, 100))
        result = hole_close(layer, max_hole_size=500)
        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_has_polygon_geometry(self):
        """Output layer geometry type is PolygonGeometry."""
        layer = _polygon_layer()
        _add(layer, _square(0, 0, 100))
        result = hole_close(layer, max_hole_size=500)
        assert result.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.integration
    def test_result_has_at_least_one_feature(self):
        """hole_close on a non-empty input produces at least one output feature."""
        layer = _polygon_layer()
        _add(layer, _square(0, 0, 100))
        result = hole_close(layer, max_hole_size=500)
        assert result.featureCount() > 0

    @pytest.mark.integration
    def test_result_geometries_are_geos_valid(self):
        """All geometries in the result pass GEOS validity check."""
        layer = _polygon_layer()
        _add(layer, _square_with_hole(outer=100, hx=20, hy=20, hole=20))
        result = hole_close(layer, max_hole_size=500)
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(), "Null geometry in result"
            assert not geom.isEmpty(), "Empty geometry in result"
            assert geom.isGeosValid(), f"Invalid geometry: {geom.validateGeometry()}"

    # -- Core domain logic ---------------------------------------------------

    @pytest.mark.integration
    def test_small_hole_is_filled(self):
        """A hole whose area is below max_hole_size is closed.

        Setup:
          Outer square: 100 × 100 = 10 000 m²
          Hole:          20 ×  20 =    400 m²  (centred at 40,40)
          Input area:              9 600 m²

        With max_hole_size = 500 the 400 m² hole is below threshold.
        Expected result area: ≈ 10 000 m² (hole filled).
        """
        layer = _polygon_layer()
        _add(layer, _square_with_hole(outer=100, hx=40, hy=40, hole=20))

        result = hole_close(layer, max_hole_size=500)

        result_area = _total_area(result)
        assert result_area == pytest.approx(10_000.0, rel=0.05), \
            f"Expected area ≈ 10 000 m² (hole filled), got {result_area:.1f} m²"

    @pytest.mark.integration
    def test_large_hole_is_not_filled(self):
        """A hole whose area exceeds max_hole_size is preserved.

        Setup:
          Outer square: 100 × 100 = 10 000 m²
          Hole:          40 ×  40 =  1 600 m²  (centred at 30,30)
          Input area:               8 400 m²

        With max_hole_size = 500 the 1 600 m² hole is above threshold.
        Expected result area: ≈ 8 400 m² (hole stays).
        """
        layer = _polygon_layer()
        _add(layer, _square_with_hole(outer=100, hx=30, hy=30, hole=40))

        result = hole_close(layer, max_hole_size=500)

        result_area = _total_area(result)
        # Area should be close to the donut area (8 400), NOT the full square (10 000)
        assert result_area == pytest.approx(8_400.0, rel=0.05), \
            f"Expected area ≈ 8 400 m² (hole kept), got {result_area:.1f} m²"

    @pytest.mark.integration
    def test_polygon_without_holes_area_unchanged(self):
        """A solid polygon (no holes) passes through unchanged.

        Setup:
          Solid square: 100 × 100 = 10 000 m²

        Expected result area: ≈ 10 000 m².
        """
        layer = _polygon_layer()
        _add(layer, _square(0, 0, 100))

        result = hole_close(layer, max_hole_size=500)

        result_area = _total_area(result)
        assert result_area == pytest.approx(10_000.0, rel=0.05), \
            f"Expected area ≈ 10 000 m² (no hole), got {result_area:.1f} m²"

    @pytest.mark.integration
    def test_result_area_increases_after_small_hole_fill(self):
        """Result area must be strictly greater than input area when a hole is filled."""
        layer = _polygon_layer()
        geom = _square_with_hole(outer=100, hx=40, hy=40, hole=20)
        _add(layer, geom)
        input_area = geom.area()  # ≈ 9 600

        result = hole_close(layer, max_hole_size=500)

        result_area = _total_area(result)
        assert result_area > input_area, \
            f"Result area {result_area:.1f} must exceed input area {input_area:.1f}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_max_hole_size_zero_fills_nothing(self):
        """max_hole_size=0 means no hole can pass the area filter → hole stays.

        Setup:
          Outer 100 × 100 with 20 × 20 hole (400 m²).
          max_hole_size = 0: even the smallest hole is above threshold.
          Expected result area: ≈ 9 600 m² (hole not filled).
        """
        layer = _polygon_layer()
        _add(layer, _square_with_hole(outer=100, hx=40, hy=40, hole=20))

        result = hole_close(layer, max_hole_size=0)

        result_area = _total_area(result)
        assert result_area == pytest.approx(9_600.0, rel=0.05), \
            f"Expected ≈ 9 600 m² (hole kept), got {result_area:.1f} m²"

    @pytest.mark.integration
    def test_multiple_holes_small_filled_large_kept(self):
        """With two holes, only the small one should be filled.

        Build a 200 × 200 polygon with:
          - small hole  20 × 20  =   400 m² at (10,10)
          - large hole  60 × 60  = 3 600 m² at (100,100)

        max_hole_size = 500:
          - small hole (400 ≤ 500) → filled
          - large hole (3 600 > 500) → kept

        Outer area   = 200 × 200      = 40 000 m²
        Input area   = 40 000 – 400 – 3 600 = 36 000 m²
        Expected     = 40 000 – 3 600        = 36 400 m²
        """
        outer = [
            QgsPointXY(0, 0),   QgsPointXY(200, 0),
            QgsPointXY(200, 200), QgsPointXY(0, 200),
            QgsPointXY(0, 0),
        ]
        small_hole = [
            QgsPointXY(10, 10), QgsPointXY(30, 10),
            QgsPointXY(30, 30), QgsPointXY(10, 30),
            QgsPointXY(10, 10),
        ]
        large_hole = [
            QgsPointXY(100, 100), QgsPointXY(160, 100),
            QgsPointXY(160, 160), QgsPointXY(100, 160),
            QgsPointXY(100, 100),
        ]
        geom = QgsGeometry.fromPolygonXY([outer, small_hole, large_hole])
        layer = _polygon_layer()
        _add(layer, geom)

        result = hole_close(layer, max_hole_size=500)

        result_area = _total_area(result)
        expected = 40_000.0 - 3_600.0  # large hole stays
        assert result_area == pytest.approx(expected, rel=0.05), \
            f"Expected ≈ {expected:.0f} m², got {result_area:.1f} m²"
