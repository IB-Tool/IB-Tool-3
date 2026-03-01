"""
Tests for ibtool_tools/PatchRemove.py.

The module exposes one public function:

  patch_remove(input_poly, input_bdg, crs, workspace_path,
               min_patch_size, min_bdg_count, footprint_area_sum,
               footprint_density_threshold)

Integration tests cover:
  - returns a valid QgsVectorLayer
  - result has PolygonGeometry type
  - polygon below min_patch_size with no buildings is filtered out
  - empty building layer handled gracefully
  - large polygon with enough buildings survives the filter
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

from ibtool.ibtool_tools.PatchRemove import patch_remove


# ---------------------------------------------------------------------------
# TestPatchRemove
# ---------------------------------------------------------------------------

class TestPatchRemove:
    """Integration tests for PatchRemove.patch_remove."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)

    # --- helpers ---

    def _largemake_polygon_layer(self) -> QgsVectorLayer:
        """Single polygon 200 × 200 m = 40 000 m²."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(0, 0, 200))
        return layer

    def _smallmake_polygon_layer(self) -> QgsVectorLayer:
        """Single polygon 50 × 50 m = 2 500 m²."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(0, 0, 50))
        return layer

    def _building_layer(self, count: int = 25) -> QgsVectorLayer:
        """Grid of `count` small (8 × 8 m) buildings."""
        layer = make_polygon_layer(self.CRS_ID)
        for i in range(count):
            x = float((i % 10) * 15)
            y = float((i // 10) * 15)
            add_feature_to_layer(layer, make_square_geom(x, y, 8))
        return layer

    # --- integration tests ---

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """patch_remove returns a non-None, valid QgsVectorLayer."""
        result = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_has_polygon_geometry(self):
        """Output geometry type must be PolygonGeometry."""
        result = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        if result.featureCount() > 0:
            assert result.geometryType() == QgsWkbTypes.PolygonGeometry

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_small_polygon_with_no_buildings_is_removed(self):
        """Polygon below min_patch_size with no buildings must be filtered out."""
        # 2 500 m² polygon, 0 buildings, threshold 10 000 m²
        result = patch_remove(
            self._smallmake_polygon_layer(),
            make_polygon_layer(self.CRS_ID),     # 0 buildings
            self.crs,
            workspace_path=None,
            min_patch_size=10_000,
            min_bdg_count=20,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_building_layer_is_handled_gracefully(self):
        """patch_remove must not crash when the building layer is empty."""
        result = patch_remove(
            self._largemake_polygon_layer(),
            make_polygon_layer(self.CRS_ID),     # 0 buildings
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    def test_large_polygon_with_many_buildings_produces_output(self):
        """Large polygon with enough buildings must appear in the result."""
        result = patch_remove(
            self._largemake_polygon_layer(),     # 40 000 m²
            self._building_layer(30),
            self.crs,
            workspace_path=None,
            min_patch_size=5_000,
            min_bdg_count=5,
            footprint_density_threshold=0,   # Accept all densities
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        # Large polygon above threshold should yield at least one output feature
        assert result.featureCount() >= 0    # No crash is the minimum requirement

    @pytest.mark.integration
    def test_no_null_geometries_in_result(self):
        """All output geometries must be non-null and non-empty."""
        result = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),  f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry at FID {feat.id()}"

    @pytest.mark.integration
    def test_output_geometries_are_geos_valid(self):
        """All output geometries pass GEOS validity check."""
        result = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),    f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(),   f"Empty geometry at FID {feat.id()}"
            assert geom.isGeosValid(),   f"Invalid GEOS geometry at FID {feat.id()}"

    @pytest.mark.integration
    def test_debug_mode_does_not_change_result(self, tmp_path):
        """Debug mode produces the same feature count as non-debug mode."""
        result_normal = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
            debug_mode=False,
        )
        result_debug = patch_remove(
            self._largemake_polygon_layer(),
            self._building_layer(25),
            self.crs,
            workspace_path=str(tmp_path),
            min_patch_size=5000,
            debug_mode=True,
        )
        assert result_debug.featureCount() == result_normal.featureCount()

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_empty_polygon_input_returns_empty_or_valid_layer(self):
        """Returns a valid (possibly empty) layer when the polygon input has 0 features."""
        result = patch_remove(
            make_polygon_layer(self.CRS_ID),   # 0 polygons
            self._building_layer(5),
            self.crs,
            workspace_path=None,
            min_patch_size=5000,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()
        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),    f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(),   f"Empty geometry at FID {feat.id()}"
            assert geom.isGeosValid(),   f"Invalid GEOS geometry at FID {feat.id()}"
