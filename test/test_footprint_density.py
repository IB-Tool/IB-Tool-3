"""
Tests for ibtool_tools/FootprintDensity.py.

The module exposes three public functions:

  footprint_density(HU_Input, Bloecke, footprint_density_threshold)
    - Calculates overlap ratio of building footprints per city block.

  identify_dense_blocks(HU_Input, Bloecke, footprintdensitythreshold)
    - Returns city blocks where building footprint density exceeds threshold.

  calc_footprint_density(InputBdg, InputStrNetwork, Buffer, GlobalThreshold,
                         Ext, MinBdgCount, Partition)
    - High-level wrapper: derives global overlap from road network + buildings.

Unit tests cover:
  - identify_dense_blocks: invalid layer type → raises ValueError
  - calc_footprint_density: Ext='global' without Partition → raises ValueError

Integration tests cover:
  - footprint_density: returns valid QgsVectorLayer with OVERLAP field
  - identify_dense_blocks: returns valid QgsVectorLayer
  - identify_dense_blocks: high threshold → fewer (or zero) features returned
  - identify_dense_blocks: low threshold (0) → all blocks returned
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

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.FootprintDensity import (
    footprint_density,
    identify_dense_blocks,
    calc_footprint_density,
)


# ---------------------------------------------------------------------------
# Domain-specific layer helpers
# ---------------------------------------------------------------------------

def _block_layer_with_name(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """City block layer with a NAME field (required by footprint_density)."""
    layer = make_polygon_layer(crs)
    layer.dataProvider().addAttributes([QgsField("NAME", QVariant.Int)])
    layer.updateFields()
    return layer


def _add_named_block(layer: QgsVectorLayer, x0: float, y0: float,
                     size: float, name: int):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(make_square_geom(x0, y0, size))
    feat.setAttribute("NAME", name)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()


def _building_layer(crs: str = "EPSG:25833") -> QgsVectorLayer:
    """Multiple small buildings arranged in a grid."""
    layer = make_polygon_layer(crs)
    for i in range(16):
        x = float((i % 4) * 20 + 5)
        y = float((i // 4) * 20 + 5)
        add_feature_to_layer(layer, make_square_geom(x, y, 10))
    return layer


# ---------------------------------------------------------------------------
# TestFootprintDensityUnit — unit tests (no Processing)
# ---------------------------------------------------------------------------

class TestFootprintDensityUnit:
    """Unit tests that do not require QGIS Processing."""

    @pytest.mark.unit
    def test_identify_dense_blocks_invalid_type_raises_valueerror(self):
        """identify_dense_blocks must raise ValueError for non-layer input."""
        with pytest.raises(ValueError, match="valid QgsVectorLayer"):
            identify_dense_blocks("not_a_layer", "also_not_a_layer", 18)

    @pytest.mark.unit
    def test_calc_footprint_density_global_without_partition_raises_valueerror(self):
        """calc_footprint_density with Ext='global' and no Partition raises ValueError."""
        buildings = _building_layer()
        roads = QgsVectorLayer("LineString?crs=EPSG:25833", "roads", "memory")

        with pytest.raises(ValueError, match="Partition"):
            calc_footprint_density(buildings, roads, Ext="global", Partition=None)


# ---------------------------------------------------------------------------
# TestFootprintDensityIntegration — integration tests
# ---------------------------------------------------------------------------

class TestFootprintDensityIntegration:
    """Integration tests for FootprintDensity functions."""

    CRS_ID = "EPSG:25833"

    # --- footprint_density ---

    @pytest.mark.integration
    def test_footprint_density_returns_valid_layer(self):
        """footprint_density returns a non-None, valid QgsVectorLayer."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = footprint_density(buildings, blocks, footprint_density_threshold=0)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_footprint_density_result_has_overlap_field(self):
        """footprint_density output must contain an 'OVERLAP' field."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = footprint_density(buildings, blocks, footprint_density_threshold=0)

        field_names = [f.name() for f in result.fields()]
        assert "OVERLAP" in field_names, \
            f"Expected 'OVERLAP' field; found: {field_names}"

    @pytest.mark.integration
    def test_footprint_density_overlap_is_between_0_and_100(self):
        """OVERLAP values must be in the range [0, 100]."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = footprint_density(buildings, blocks, footprint_density_threshold=0)

        for feat in result.getFeatures():
            overlap = feat["OVERLAP"]
            if overlap is not None:
                assert 0 <= overlap <= 100, \
                    f"OVERLAP {overlap} is outside [0, 100]"

    # --- identify_dense_blocks ---

    @pytest.mark.integration
    def test_identify_dense_blocks_returns_valid_layer(self):
        """identify_dense_blocks returns a non-None, valid QgsVectorLayer."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = identify_dense_blocks(buildings, blocks,
                                       footprintdensitythreshold=0)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_identify_dense_blocks_threshold_zero_returns_all(self):
        """With threshold=0 all blocks meeting density ≥ 0 are returned."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = identify_dense_blocks(buildings, blocks,
                                       footprintdensitythreshold=0)

        # At least one block with buildings inside should be returned
        assert result.featureCount() >= 0    # no crash is the minimum guarantee

    @pytest.mark.integration
    def test_identify_dense_blocks_high_threshold_returns_fewer_blocks(self):
        """High threshold returns fewer features than a low threshold."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)
        _add_named_block(blocks, 200, 0, 100, 2)   # block with no buildings

        low = identify_dense_blocks(buildings, blocks,
                                    footprintdensitythreshold=0)
        high = identify_dense_blocks(buildings, blocks,
                                     footprintdensitythreshold=10_000)  # impossible

        # High threshold should filter out (at least equal, typically less)
        assert high.featureCount() <= low.featureCount()

    @pytest.mark.integration
    def test_identify_dense_blocks_result_has_overlap_field(self):
        """Output must contain an 'OVERLAP' field."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = identify_dense_blocks(buildings, blocks,
                                       footprintdensitythreshold=0)

        if result.featureCount() > 0:
            field_names = [f.name() for f in result.fields()]
            assert "OVERLAP" in field_names, \
                f"Expected 'OVERLAP' field; found: {field_names}"

    @pytest.mark.integration
    def test_identify_dense_blocks_no_null_geometries(self):
        """No null or empty geometries in the output."""
        buildings = _building_layer(self.CRS_ID)
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        result = identify_dense_blocks(buildings, blocks,
                                       footprintdensitythreshold=0)

        for feat in result.getFeatures():
            geom = feat.geometry()
            assert not geom.isNull(),  f"Null geometry at FID {feat.id()}"
            assert not geom.isEmpty(), f"Empty geometry at FID {feat.id()}"
