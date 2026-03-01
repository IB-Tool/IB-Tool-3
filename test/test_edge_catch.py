"""
Tests for ibtool_tools/EdgeCatch.py.

The module exposes one public function:

  edge_catch(grouped_bdgs, hu_input, road_network, bloecke, crs,
             workspace_path, debug_mode=False)

Unit tests cover:
  - empty road network (after filtering) → grouped_bdgs returned unchanged
  - empty grouped_bdgs → no crash

Integration tests cover:
  - returns a valid QgsVectorLayer
  - output geometry type is PolygonGeometry
  - all output geometries are GEOS-valid
  - road between groups triggers snapping algorithm (non-empty output)
  - debug_mode=True does not raise
  - debug_mode does not change feature count (invariant)

Edge case tests cover:
  - road layer with mismatched CRS does not crash

Performance tests cover:
  - 100 road segments complete within 30 seconds
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

# QGIS must be initialised before any layer is created
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.EdgeCatch import edge_catch


# ---------------------------------------------------------------------------
# TestEdgeCatch
# ---------------------------------------------------------------------------

class TestEdgeCatch:
    """Tests for EdgeCatch.edge_catch."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        cls.crs = QgsCoordinateReferenceSystem(cls.CRS_ID)

    # --- helpers ---

    def _grouped_buildings(self) -> QgsVectorLayer:
        """Two non-overlapping building groups."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(0,   0, 80))
        add_feature_to_layer(layer, make_square_geom(200, 0, 80))
        return layer

    def _hu_input(self) -> QgsVectorLayer:
        """Individual building footprints inside the groups."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(10, 10, 20))
        add_feature_to_layer(layer, make_square_geom(210, 10, 20))
        return layer

    def _empty_road_layer(self) -> QgsVectorLayer:
        return make_line_layer(self.CRS_ID)

    def _road_layer_near_buildings(self) -> QgsVectorLayer:
        """A road segment running between the two building groups."""
        layer = make_line_layer(self.CRS_ID)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(150, -20), QgsPointXY(150, 120),
        ]))
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    def _block_layer(self) -> QgsVectorLayer:
        """One large block covering the full test area."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(-50, -50, 450))
        return layer

    # --- unit tests ---

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_road_network_returns_grouped_bdgs(self):
        """No road segments near buildings → grouped_bdgs returned as-is."""
        grouped = self._grouped_buildings()
        expected_count = grouped.featureCount()

        result = edge_catch(
            grouped, self._hu_input(), self._empty_road_layer(),
            self._block_layer(), self.crs, workspace_path=None,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == expected_count

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_grouped_buildings_no_crash(self):
        """Empty grouped_bdgs layer must not raise an exception."""
        grouped = make_polygon_layer(self.CRS_ID)  # 0 features

        result = edge_catch(
            grouped, self._hu_input(), self._empty_road_layer(),
            self._block_layer(), self.crs, workspace_path=None,
        )

        assert result is not None

    # --- integration tests ---

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """edge_catch returns a non-None, valid QgsVectorLayer."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_geometry_type_is_polygon(self):
        """Every feature in the result must be a polygon."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None,
        )

        for feat in result.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isNull() and not geom.isEmpty():
                assert geom.type() == QgsWkbTypes.PolygonGeometry, \
                    f"Expected polygon, got geometry type {geom.type()}"

    @pytest.mark.integration
    def test_result_geometries_are_not_null(self):
        """No null or empty geometries in the output."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None,
        )

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(), f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry at FID {feat.id()}"

    @pytest.mark.integration
    def test_debug_mode_does_not_crash(self, tmp_path):
        """edge_catch with debug_mode=True must not raise."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._empty_road_layer(), self._block_layer(),
            self.crs, workspace_path=str(tmp_path), debug_mode=True,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    # --- new tests (test-plan step 5) ---

    @pytest.mark.integration
    def test_output_geometries_are_geos_valid(self):
        """All output geometries pass GEOS validity when the road network is present."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None,
        )

        assert result is not None
        for feat in result.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isNull() and not geom.isEmpty():
                assert geom.isGeosValid(), \
                    f"GEOS-invalid geometry at FID {feat.id()}: {geom.lastError()}"

    @pytest.mark.integration
    def test_road_between_groups_produces_non_empty_output(self):
        """Road running between building groups triggers snapping and yields at least one feature."""
        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() >= 1
        for feat in result.getFeatures():
            geom = feat.geometry()
            if not geom.isNull() and not geom.isEmpty():
                assert geom.isGeosValid(), f"GEOS-invalid at FID {feat.id()}"

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_mismatched_crs_road_layer_does_not_crash(self):
        """Road layer in EPSG:4326 must not raise — roads will not overlap buildings and are filtered out."""
        road_wgs84 = make_line_layer("EPSG:4326")
        feat = QgsFeature(road_wgs84.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(13.4, 52.5), QgsPointXY(13.5, 52.5),
        ]))
        road_wgs84.dataProvider().addFeatures([feat])
        road_wgs84.updateExtents()

        result = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            road_wgs84, self._block_layer(),
            self.crs, workspace_path=None,
        )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.integration
    def test_debug_mode_produces_same_feature_count(self, tmp_path):
        """Debug mode does not alter the feature count of the result."""
        result_normal = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=None, debug_mode=False,
        )
        result_debug = edge_catch(
            self._grouped_buildings(), self._hu_input(),
            self._road_layer_near_buildings(), self._block_layer(),
            self.crs, workspace_path=str(tmp_path), debug_mode=True,
        )

        assert result_debug.featureCount() == result_normal.featureCount()

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_performance_with_large_road_network(self, tmp_path):
        """edge_catch with 100 road segments completes within 30 seconds."""
        import time

        grouped = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(grouped, make_square_geom(0,   0, 200))
        add_feature_to_layer(grouped, make_square_geom(400, 0, 200))

        hu = make_polygon_layer(self.CRS_ID)
        for i in range(10):
            add_feature_to_layer(hu, make_square_geom(float(i * 18),       10.0, 14))
            add_feature_to_layer(hu, make_square_geom(float(400 + i * 18), 10.0, 14))

        road = make_line_layer(self.CRS_ID)
        for i in range(100):
            y = float(i * 3)
            seg = QgsFeature(road.fields())
            seg.setGeometry(QgsGeometry.fromPolylineXY([
                QgsPointXY(260.0, y), QgsPointXY(340.0, y),
            ]))
            road.dataProvider().addFeatures([seg])
        road.updateExtents()

        blocks = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(blocks, make_square_geom(-50, -50, 750))

        start = time.time()
        result = edge_catch(grouped, hu, road, blocks, self.crs,
                            workspace_path=str(tmp_path))
        elapsed = time.time() - start

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert elapsed < 30.0, f"edge_catch took {elapsed:.1f}s — expected < 30s"


    # --- merge-block coverage (mocked process_single_feature) ---

    @pytest.mark.unit
    def test_merge_block_executes_when_process_returns_layer(self):
        """Merge block at lines 80-89 runs when process_single_feature returns a layer."""
        from unittest.mock import patch
        # Build a minimal single-polygon result to return from the mock
        result_layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(result_layer, make_square_geom(0, 0, 50))

        with patch(
            "ibtool.ibtool_tools.EdgeCatch.process_single_feature",
            return_value=result_layer,
        ):
            result = edge_catch(
                self._grouped_buildings(), self._hu_input(),
                self._road_layer_near_buildings(), self._block_layer(),
                self.crs, workspace_path=None,
            )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() >= 1

    @pytest.mark.unit
    def test_merge_block_handles_exception_gracefully(self):
        """An exception inside the merge block is caught; function returns a result."""
        from unittest.mock import patch

        def _raise_on_call(*args, **kwargs):
            raise RuntimeError("merge failed")

        result_layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(result_layer, make_square_geom(0, 0, 50))

        call_count = [0]

        def _side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return result_layer
            raise RuntimeError("merge failed")

        with patch(
            "ibtool.ibtool_tools.EdgeCatch.process_single_feature",
            side_effect=_side_effect,
        ), patch(
            "ibtool.ibtool_tools.EdgeCatch.processing.run",
            side_effect=RuntimeError("native:mergevectorlayers failed"),
        ):
            result = edge_catch(
                self._grouped_buildings(), self._hu_input(),
                self._road_layer_near_buildings(), self._block_layer(),
                self.crs, workspace_path=None,
            )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)

    @pytest.mark.unit
    def test_all_features_return_none_falls_back_to_grouped_bdgs(self):
        """When all process_single_feature calls return None, fallback to grouped_bdgs."""
        from unittest.mock import patch

        grouped = self._grouped_buildings()
        with patch(
            "ibtool.ibtool_tools.EdgeCatch.process_single_feature",
            return_value=None,
        ):
            result = edge_catch(
                grouped, self._hu_input(),
                self._road_layer_near_buildings(), self._block_layer(),
                self.crs, workspace_path=None,
            )

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        # polygons_merge stays None → fallback to grouped_bdgs
        assert result.featureCount() == grouped.featureCount()
