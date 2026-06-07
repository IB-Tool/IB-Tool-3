"""
Tests for ibtool_tools/ErodeEmptyAreas.py.

The module exposes one public function:

  erode_empty_areas(input_layer, buildings_layer,
                    min_empty_area=500.0, min_buffer_m=10.0, max_buffer_m=100.0,
                    workspace_path=None, debug_mode=False)

Buffer scaling formula:
  buf_dist = clamp(sqrt(building_area), min_buffer_m, max_buffer_m)

Unit tests cover (no Processing — early return branches):
  - empty input layer → returns input unchanged
  - invalid input layer → returns input unchanged
  - empty buildings layer → returns input unchanged
"""

import pytest
from qgis.core import QgsVectorLayer

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.ErodeEmptyAreas import erode_empty_areas


class TestErodeEmptyAreasEarlyReturn:
    """Unit tests for erode_empty_areas early-return branches (no Processing)."""

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_input_returns_input_unchanged(self):
        """erode_empty_areas on a valid but empty settlement layer returns input unchanged."""
        settlement = make_polygon_layer()   # 0 features
        buildings = make_polygon_layer()
        add_feature_to_layer(buildings, make_square_geom(0, 0, 10))

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_invalid_input_layer_returns_early(self):
        """erode_empty_areas on an uninitialised QgsVectorLayer returns without crash."""
        invalid_layer = QgsVectorLayer()    # uninitialised
        buildings = make_polygon_layer()
        add_feature_to_layer(buildings, make_square_geom(0, 0, 10))

        result = erode_empty_areas(invalid_layer, buildings)

        assert result is not None
        assert result is invalid_layer

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_buildings_returns_settlement_unchanged(self):
        """erode_empty_areas with 0 buildings returns the settlement layer unchanged."""
        settlement = make_polygon_layer()
        add_feature_to_layer(settlement, make_square_geom(0, 0, 100))
        buildings = make_polygon_layer()   # 0 features

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() > 0   # settlement returned as-is
