import pytest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
    QgsWkbTypes,
    QgsProject,
)
from PyQt5.QtCore import QVariant

from test.utilities import get_qgis_app
from ibtool.ibtool_tools.AddSingleBuilding import add_single_bdg


# ---------------------------------------------------------------------------
# Layer helpers
# ---------------------------------------------------------------------------

def _make_polygon_layer(crs_epsg="EPSG:25833"):
    """In-memory polygon layer with ``id`` (Int) and ``Area`` (Double) fields."""
    layer = QgsVectorLayer(f"Polygon?crs={crs_epsg}", "test", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("id", QVariant.Int),
        QgsField("Area", QVariant.Double),
    ])
    layer.updateFields()
    assert layer.isValid(), "Test layer must be valid"
    return layer


def _add_building(layer, fid, area, coords):
    """Add a single polygon feature to *layer* with the given ``id`` and ``Area``."""
    feature = QgsFeature(layer.fields())
    feature.setAttribute("id", fid)
    feature.setAttribute("Area", area)
    feature.setGeometry(
        QgsGeometry.fromPolygonXY([[QgsPointXY(x, y) for x, y in coords]])
    )
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestAddSingleBuilding:
    """
    Tests for ``add_single_bdg`` in AddSingleBuilding.py.

    Scenario layout (EPSG:25833, coordinates in metres):
      cluster polygon : (0,0)–(100,100)

      Building A : centroid (50, 50)  — inside cluster,  Area=25   → filtered (inside)
      Building B : centroid (70, 70)  — inside cluster,  Area=500  → filtered (inside)
      Building C : centroid (200,200) — outside cluster, Area=25   → filtered (too small)
      Building D : centroid (300,300) — outside cluster, Area=500  → IN OUTPUT
    """

    @classmethod
    def setup_class(cls):
        cls.QGIS_APP, cls.CANVAS, cls.IFACE, cls.PARENT = get_qgis_app()
        cls.crs = QgsCoordinateReferenceSystem("EPSG:25833")

    def teardown_method(self, method):
        QgsProject.instance().clear()

    # --- shared fixture -------------------------------------------------

    def _make_scenario_layers(self):
        crs = "EPSG:25833"

        cluster = _make_polygon_layer(crs)
        _add_building(cluster, 1, 10000, [
            (0, 0), (100, 0), (100, 100), (0, 100), (0, 0)
        ])

        buildings = _make_polygon_layer(crs)
        # A – inside, small
        _add_building(buildings, 1, 25.0,  [(45, 45),  (55, 45),  (55, 55),  (45, 55),  (45, 45)])
        # B – inside, large
        _add_building(buildings, 2, 500.0, [(60, 60),  (80, 60),  (80, 80),  (60, 80),  (60, 60)])
        # C – outside, small
        _add_building(buildings, 3, 25.0,  [(195, 195), (205, 195), (205, 205), (195, 205), (195, 195)])
        # D – outside, large  →  expected in output
        _add_building(buildings, 4, 500.0, [(280, 280), (320, 280), (320, 320), (280, 320), (280, 280)])

        return buildings, cluster

    # --- normal cases ---------------------------------------------------

    @pytest.mark.integration
    def test_returns_valid_layer(self):
        """Result must be a valid QgsVectorLayer."""
        buildings, cluster = self._make_scenario_layers()
        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_normal_case_feature_count(self):
        """Only the one large building outside the cluster produces output."""
        buildings, cluster = self._make_scenario_layers()
        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result.featureCount() == 1, (
            f"Expected 1 feature (only Building D), got {result.featureCount()}"
        )

    @pytest.mark.integration
    def test_output_geometries_are_valid(self):
        """Every output geometry must be non-null, non-empty, GEOS-valid, and a polygon."""
        buildings, cluster = self._make_scenario_layers()
        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),    "Output geometry must not be null"
            assert not geom.isEmpty(),   "Output geometry must not be empty"
            assert geom.isGeosValid(),   "Output geometry must be GEOS-valid"
            assert geom.type() == QgsWkbTypes.PolygonGeometry, (
                "Output geometry must be polygon type"
            )

    @pytest.mark.integration
    def test_multiple_large_buildings_outside_cluster(self):
        """Each large building outside the cluster produces exactly one bounding rect."""
        crs = "EPSG:25833"
        cluster = _make_polygon_layer(crs)
        _add_building(cluster, 1, 10000, [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])

        buildings = _make_polygon_layer(crs)
        _add_building(buildings, 1, 400.0, [(200, 200), (230, 200), (230, 230), (200, 230), (200, 200)])
        _add_building(buildings, 2, 500.0, [(300, 300), (330, 300), (330, 330), (300, 330), (300, 300)])
        _add_building(buildings, 3, 600.0, [(400, 400), (435, 400), (435, 435), (400, 435), (400, 400)])

        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result.featureCount() == 3, (
            f"Expected one bounding rect per large building, got {result.featureCount()}"
        )

    @pytest.mark.integration
    def test_custom_threshold_respected(self):
        """Custom threshold value filters correctly (geometric area > threshold).

        Note: an empty cluster layer causes all centroids to be treated as
        disjoint (no polygon to intersect with), so all buildings are candidates.

        shp_area2 (called inside add_single_bdg) overwrites the Area attribute
        with the polygon's computed geometric area, so polygon size determines
        which features pass the threshold filter — not the Area value passed to
        _add_building.
          Building 1: 10×10 = 100 m²  →  below threshold 200  →  excluded
          Building 2: 20×20 = 400 m²  →  above threshold 200  →  included
        """
        crs = "EPSG:25833"
        cluster = _make_polygon_layer(crs)  # empty — all buildings outside

        buildings = _make_polygon_layer(crs)
        # 10×10 square → geometric area 100 m² < threshold 200
        _add_building(buildings, 1, 100.0, [(0,  0),  (10, 0),  (10, 10), (0,  10), (0,  0)])
        # 20×20 square → geometric area 400 m² > threshold 200
        _add_building(buildings, 2, 400.0, [(50, 50), (70, 50), (70, 70), (50, 70), (50, 50)])

        result = add_single_bdg(buildings, cluster, self.crs, threshold=200)

        assert result.featureCount() == 1, (
            f"Only the 20x20 building (400 m²) should pass threshold=200, got {result.featureCount()}"
        )

    # --- edge cases -----------------------------------------------------

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_input_buildings(self):
        """Empty input_hu must return a valid empty layer without crashing."""
        crs = "EPSG:25833"
        buildings = _make_polygon_layer(crs)
        cluster = _make_polygon_layer(crs)
        _add_building(cluster, 1, 10000, [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])

        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_all_buildings_inside_cluster(self):
        """Buildings inside the cluster must never appear in the output."""
        crs = "EPSG:25833"
        cluster = _make_polygon_layer(crs)
        _add_building(cluster, 1, 1_000_000, [
            (0, 0), (10000, 0), (10000, 10000), (0, 10000), (0, 0)
        ])

        buildings = _make_polygon_layer(crs)
        _add_building(buildings, 1, 500.0, [(100, 100), (130, 100), (130, 130), (100, 130), (100, 100)])
        _add_building(buildings, 2, 800.0, [(200, 200), (240, 200), (240, 240), (200, 240), (200, 200)])

        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result is not None
        assert result.featureCount() == 0, (
            "Buildings inside cluster should not appear in output"
        )

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_all_buildings_below_threshold(self):
        """Buildings outside the cluster but below threshold must not appear in output."""
        crs = "EPSG:25833"
        cluster = _make_polygon_layer(crs)
        _add_building(cluster, 1, 10000, [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])

        buildings = _make_polygon_layer(crs)
        _add_building(buildings, 1, 50.0,  [(200, 200), (210, 200), (210, 210), (200, 210), (200, 200)])
        _add_building(buildings, 2, 100.0, [(300, 300), (308, 300), (308, 308), (300, 308), (300, 300)])

        result = add_single_bdg(buildings, cluster, self.crs, threshold=300)

        assert result is not None
        assert result.featureCount() == 0, "No features should pass threshold filter"

    # --- teardown -------------------------------------------------------

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, 'QGIS_APP') and cls.QGIS_APP:
            cls.QGIS_APP.exitQgis()
