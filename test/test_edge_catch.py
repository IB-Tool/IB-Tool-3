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

# QGIS must be initialised before any layer is created
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.ibtool_tools.EdgeCatch import edge_catch


# ---------------------------------------------------------------------------
# Geometry / layer factory helpers
# ---------------------------------------------------------------------------

def _polygon_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Empty in-memory polygon layer."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", "test_poly", "memory")
    layer.updateFields()
    return layer


def _line_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Empty in-memory line layer."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", "test_line", "memory")
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


def _add(layer: QgsVectorLayer, geom: QgsGeometry) -> QgsFeature:
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat


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
        layer = _polygon_layer(self.CRS_ID)
        _add(layer, _square(0,   0, 80))
        _add(layer, _square(200, 0, 80))
        return layer

    def _hu_input(self) -> QgsVectorLayer:
        """Individual building footprints inside the groups."""
        layer = _polygon_layer(self.CRS_ID)
        _add(layer, _square(10, 10, 20))
        _add(layer, _square(210, 10, 20))
        return layer

    def _empty_road_layer(self) -> QgsVectorLayer:
        return _line_layer(self.CRS_ID)

    def _road_layer_near_buildings(self) -> QgsVectorLayer:
        """A road segment running between the two building groups."""
        layer = _line_layer(self.CRS_ID)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(150, -20), QgsPointXY(150, 120),
        ]))
        layer.dataProvider().addFeatures([feat])
        layer.updateExtents()
        return layer

    def _block_layer(self) -> QgsVectorLayer:
        """One large block covering the full test area."""
        layer = _polygon_layer(self.CRS_ID)
        _add(layer, _square(-50, -50, 450))
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
        grouped = _polygon_layer(self.CRS_ID)  # 0 features

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
