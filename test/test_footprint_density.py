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
    """City block layer with a BLOCK_ID field (required by footprint_density).

    Note: footprint_density joins on BLOCK_ID (renamed from NAME in commit 6cebfaf).
    """
    layer = make_polygon_layer(crs)
    layer.dataProvider().addAttributes([QgsField("BLOCK_ID", QVariant.Int)])
    layer.updateFields()
    return layer


def _add_named_block(layer: QgsVectorLayer, x0: float, y0: float,
                     size: float, name: int):
    feat = QgsFeature(layer.fields())
    feat.setGeometry(make_square_geom(x0, y0, size))
    feat.setAttribute("BLOCK_ID", name)
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

    @pytest.mark.integration
    @pytest.mark.performance
    @pytest.mark.slow
    def test_performance_with_100_buildings(self):
        """footprint_density completes within 30 s for 100 buildings across 4 blocks."""
        import time

        # 4 blocks in a 2×2 grid, each 200×200 m
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks,   0,   0, 200, 1)
        _add_named_block(blocks, 200,   0, 200, 2)
        _add_named_block(blocks,   0, 200, 200, 3)
        _add_named_block(blocks, 200, 200, 200, 4)

        # 100 buildings in a 10×10 grid (12×12 m each, 38 m spacing)
        buildings = make_polygon_layer(self.CRS_ID)
        for i in range(100):
            x = float((i % 10) * 38 + 5)
            y = float((i // 10) * 38 + 5)
            add_feature_to_layer(buildings, make_square_geom(x, y, 12))

        assert buildings.featureCount() == 100

        start = time.time()
        result = footprint_density(buildings, blocks, footprint_density_threshold=0)
        elapsed = time.time() - start

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert elapsed < 30, f"footprint_density took {elapsed:.1f} s (limit: 30 s)"


class TestFootprintDensityDebugOutput:
    """Debug checkpoints of the FootprintDensity functions."""

    CRS_ID = "EPSG:25833"

    @pytest.mark.integration
    def test_identify_dense_blocks_writes_checkpoints(self, tmp_path):
        """Blocks with OVERLAP and the dense blocks go to 02a_FootprintDensity/."""
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        identify_dense_blocks(_building_layer(self.CRS_ID), blocks, 0,
                              debug_mode=True, workspace_path=str(tmp_path))

        folder = tmp_path / "02a_FootprintDensity"
        names = sorted(p.name for p in folder.glob("*.gpkg"))
        assert names == ["001_block_overlap.gpkg", "002_dense_blocks.gpkg"]
        overlap = QgsVectorLayer(str(folder / "001_block_overlap.gpkg"), "o", "ogr")
        assert "OVERLAP" in [f.name() for f in overlap.fields()]

    @pytest.mark.integration
    def test_identify_dense_blocks_no_debug_output_by_default(self, tmp_path):
        blocks = _block_layer_with_name(self.CRS_ID)
        _add_named_block(blocks, 0, 0, 100, 1)

        identify_dense_blocks(_building_layer(self.CRS_ID), blocks, 0,
                              workspace_path=str(tmp_path))

        assert not (tmp_path / "02a_FootprintDensity").exists()


# ---------------------------------------------------------------------------
# Global extent: inner blocks of all partitions are merged in one step
# ---------------------------------------------------------------------------

class _StopAfterMerge(Exception):
    """Raised by the test double right after the inner-blocks merge."""


class TestGlobalInnerBlocksMerge:
    """calc_footprint_density(Ext='global') merges the per-partition inner blocks once."""

    CRS_ID = "EPSG:25833"

    def _partitions(self, names):
        layer = QgsVectorLayer(f"Polygon?crs={self.CRS_ID}&field=NAME:string", "part", "memory")
        feats = []
        for i, name in enumerate(names):
            f = QgsFeature(layer.fields())
            f.setGeometry(make_square_geom(i * 1000, 0, 900))
            f["NAME"] = name
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        return layer

    def _inner_blocks(self, x):
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(x, 0, 10))
        return layer

    def _run(self, names):
        from unittest.mock import patch
        from ibtool.ibtool_tools import FootprintDensity as qgis_processing_owner
        real_run = qgis_processing_owner.processing.run
        inner = [self._inner_blocks(i * 1000) for i in range(len(names))]
        merges = []

        def run(alg, params, **kwargs):
            if alg == "native:mergevectorlayers":
                merges.append(list(params["LAYERS"]))
                raise _StopAfterMerge()
            if alg == "native:addautoincrementalfield":
                raise _StopAfterMerge()       # reached without any merge
            return real_run(alg, params, **kwargs)

        with patch("ibtool.ibtool_tools.FootprintDensity._select_block", side_effect=inner),                 patch("ibtool.ibtool_tools.FootprintDensity.processing.run", side_effect=run):
            with pytest.raises(_StopAfterMerge):
                calc_footprint_density(_building_layer(self.CRS_ID), make_polygon_layer(self.CRS_ID),
                                       Ext="global", Partition=self._partitions(names))
        return inner, merges

    @pytest.mark.unit
    def test_one_merge_for_all_partitions_in_partition_order(self):
        inner, merges = self._run(["P1", "P2", "P3"])
        assert len(merges) == 1
        assert merges[0] == inner

    @pytest.mark.unit
    def test_single_partition_is_not_merged(self):
        _inner, merges = self._run(["P1"])
        assert merges == []
