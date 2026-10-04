# -*- coding: utf-8 -*-
"""Tests for ibtool_tools/ErodeEmptyAreas.py.

The module exposes one public function:

  erode_empty_areas(input_layer, buildings_layer,
                    min_empty_area=500.0, min_buffer_m=10.0, max_buffer_m=100.0,
                    contact_threshold_pct=20.0, workspace_path=None, debug_mode=False)

Buffer scaling formula:
  buf_dist = clamp(sqrt(building_area), min_buffer_m, max_buffer_m)

Unit tests cover (no Processing — early return branches):
  - empty input layer → returns layer with 0 features
  - invalid input layer → returns without crash
  - empty buildings layer → returns settlement unchanged

Unit tests cover _build_buffer_layer (no Processing):
  - empty building layer → 0 buffer features
  - one building → exactly one buffer feature
  - buffer geometry is GEOS-valid
  - small building (area < min_buffer²) → buffer radius clamped to min_buffer_m
  - large building (area > max_buffer²) → buffer radius clamped to max_buffer_m
  - null-geometry building silently skipped
  - multiple buildings → matching buffer count

Integration tests cover _contact_fraction_filter (contact = share of the void
perimeter on the settlement OUTER boundary; see issue #168):
  - void with low outer contact (~9 %) returned for removal at default 20 %
  - void with high outer contact (50 %) not returned at default 20 %
  - frame void (~77 % outer contact) not returned even at threshold 50 %
  - frame void returned at threshold 80 % (perimeter includes the inner ring)
  - interior void (0 % contact) never returned

Integration tests cover:
  - returns valid QgsVectorLayer
  - output geometries are GEOS-valid
  - fringe void (contact ≥ 20 %) kept when threshold is default (20 %)
  - corner-building void (~94 % outer contact) kept at default threshold
  - any void (contact < 100 %) removed when permissive threshold (100 %) is used
  - very large min_empty_area filters all voids → returned unchanged
  - debug_mode=True produces same feature count as debug_mode=False
  - null-geometry building in buildings_layer: no crash, valid result
"""

import math
import pytest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
)

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, make_square_geom, add_feature_to_layer

from ibtool.ibtool_tools.ErodeEmptyAreas import (
    erode_empty_areas,
    _build_buffer_layer,
    _contact_fraction_filter,
    MIN_BUFFER_M,
    MAX_BUFFER_M,
    MIN_EMPTY_AREA_M2,
    BOUNDARY_CONTACT_THRESHOLD_PCT,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _total_area(layer: QgsVectorLayer) -> float:
    """Return the summed geometry area of all non-null features."""
    return sum(
        f.geometry().area()
        for f in layer.getFeatures()
        if f.geometry() and not f.geometry().isNull() and not f.geometry().isEmpty()
    )


def _all_geos_valid(layer: QgsVectorLayer) -> bool:
    """Return True when every non-null geometry passes GEOS validity."""
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom and not geom.isNull() and not geom.isEmpty():
            if not geom.isGeosValid():
                return False
    return True


# ---------------------------------------------------------------------------
# TestErodeEmptyAreasEarlyReturn — unit tests (no Processing)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TestBuildBufferLayer — unit tests for the private helper (no Processing)
# ---------------------------------------------------------------------------

class TestBuildBufferLayer:
    """Unit tests for the _build_buffer_layer private helper."""

    CRS_ID = "EPSG:25833"

    def _building_layer(self, left: float, bottom: float, size: float) -> QgsVectorLayer:
        """Single-building polygon layer at (left, bottom) with given side length."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(left, bottom, size))
        return layer

    @pytest.mark.unit
    def test_empty_building_layer_produces_empty_buffer_layer(self):
        """Empty buildings layer produces a buffer layer with 0 features."""
        layer = make_polygon_layer(self.CRS_ID)
        result = _build_buffer_layer(layer, MIN_BUFFER_M, MAX_BUFFER_M)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.featureCount() == 0

    @pytest.mark.unit
    def test_one_building_produces_one_buffer(self):
        """One valid building produces exactly one buffer feature."""
        layer = self._building_layer(0, 0, 50)   # 50×50 = 2 500 m²
        result = _build_buffer_layer(layer, MIN_BUFFER_M, MAX_BUFFER_M)

        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_buffer_geometry_is_geos_valid(self):
        """Buffer polygon produced from a valid building must pass GEOS validity."""
        layer = self._building_layer(0, 0, 50)
        result = _build_buffer_layer(layer, MIN_BUFFER_M, MAX_BUFFER_M)

        feat = next(result.getFeatures())
        geom = feat.geometry()
        assert not geom.isNull(),   "Buffer geometry must not be null"
        assert not geom.isEmpty(),  "Buffer geometry must not be empty"
        assert geom.isGeosValid(),  "Buffer geometry must be GEOS-valid"

    @pytest.mark.unit
    def test_small_building_buffer_clamped_to_min_buffer_m(self):
        """Building with sqrt(area) < min_buffer_m uses min_buffer_m as buffer radius.

        Building 2×2 = 4 m², sqrt(4) = 2 < MIN_BUFFER_M=10 → buf_dist = 10 m.
        Buffer area must exceed a full disc of radius 10 m (≈ 314 m²).
        """
        layer = self._building_layer(0, 0, 2)   # 2×2 = 4 m²
        result = _build_buffer_layer(layer, min_buffer_m=10, max_buffer_m=100)

        assert result.featureCount() == 1
        buf_area = next(result.getFeatures()).geometry().area()
        min_expected = math.pi * 10 ** 2 * 0.9   # 90 % of disc area (polygon approx)
        assert buf_area > min_expected, \
            f"Expected buffer area > {min_expected:.1f} m², got {buf_area:.1f} m²"

    @pytest.mark.unit
    def test_large_building_buffer_clamped_to_max_buffer_m(self):
        """Building with sqrt(area) > max_buffer_m uses max_buffer_m as buffer radius.

        Building 400×400 = 160 000 m², sqrt = 400 > MAX_BUFFER_M=100 → buf_dist = 100 m.
        Buffered area must exceed the building footprint alone (160 000 m²).
        """
        layer = self._building_layer(0, 0, 400)   # 400×400 = 160 000 m²
        result = _build_buffer_layer(layer, min_buffer_m=10, max_buffer_m=100)

        assert result.featureCount() == 1
        buf_area = next(result.getFeatures()).geometry().area()
        assert buf_area > 160_000, \
            f"Buffered area ({buf_area:.0f} m²) should exceed building area (160 000 m²)"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_geometry_building_is_silently_skipped(self):
        """A building feature with null geometry is skipped; buffer layer stays empty."""
        layer = make_polygon_layer(self.CRS_ID)
        null_feat = QgsFeature(layer.fields())
        # geometry not set → null
        layer.dataProvider().addFeatures([null_feat])

        result = _build_buffer_layer(layer, MIN_BUFFER_M, MAX_BUFFER_M)

        assert result.featureCount() == 0

    @pytest.mark.unit
    def test_multiple_buildings_produce_matching_buffer_count(self):
        """Three valid buildings each produce one buffer; total buffer count = 3."""
        layer = make_polygon_layer(self.CRS_ID)
        add_feature_to_layer(layer, make_square_geom(0,   0, 50))
        add_feature_to_layer(layer, make_square_geom(200, 0, 50))
        add_feature_to_layer(layer, make_square_geom(400, 0, 50))

        result = _build_buffer_layer(layer, MIN_BUFFER_M, MAX_BUFFER_M)

        assert result.featureCount() == 3


# ---------------------------------------------------------------------------
# TestContactFractionFilter — integration tests for the private helper
# ---------------------------------------------------------------------------

class TestContactFractionFilter:
    """Integration tests for _contact_fraction_filter with hand-built voids.

    Contact is the share of a void's perimeter that runs along the settlement
    OUTER boundary. Voids are removed only when 0 % < contact < threshold.
    Regression for #168: the void outlines must not become part of the
    reference boundary (that measured contact with the remaining settlement).
    """

    CRS_ID = "EPSG:25833"

    def _settlement(self) -> QgsVectorLayer:
        """Return a 200 × 200 m settlement polygon layer."""
        layer = make_polygon_layer(self.CRS_ID, "settlement")
        add_feature_to_layer(layer, make_square_geom(0, 0, 200))
        return layer

    def _void_layer(self, geom: QgsGeometry) -> QgsVectorLayer:
        """Single-void polygon layer."""
        layer = make_polygon_layer(self.CRS_ID, "voids")
        add_feature_to_layer(layer, geom)
        return layer

    @staticmethod
    def _rect(xmin, ymin, xmax, ymax) -> QgsGeometry:
        return QgsGeometry.fromRect(QgsRectangle(xmin, ymin, xmax, ymax))

    @pytest.mark.integration
    def test_low_contact_void_returned_at_default_threshold(self):
        """Void (95,0)-(105,150) touching the south edge over 10 m → removed.

        Measured contact = 30 m of 320 m ≈ 9 %: every 10 m boundary segment that
        touches the 0.5 m snap strip counts in full, so the two side segments
        adjoining the edge are included as well.
        """
        voids = self._void_layer(self._rect(95, 0, 105, 150))

        result = _contact_fraction_filter(
            self._settlement(), voids, BOUNDARY_CONTACT_THRESHOLD_PCT)

        assert result.featureCount() == 1

    @pytest.mark.integration
    def test_high_contact_void_not_returned_at_default_threshold(self):
        """Strip (0,0)-(200,40): 240 m of 480 m perimeter on the edge = 50 % → kept."""
        voids = self._void_layer(self._rect(0, 0, 200, 40))

        result = _contact_fraction_filter(
            self._settlement(), voids, BOUNDARY_CONTACT_THRESHOLD_PCT)

        assert result.featureCount() == 0

    @pytest.mark.integration
    def test_frame_void_not_returned_at_threshold_50(self):
        """Frame (200×200 minus inner 60×60): 800 m of 1 040 m ≈ 77 % → kept at 50 %."""
        frame = self._rect(0, 0, 200, 200).difference(self._rect(70, 70, 130, 130))
        voids = self._void_layer(frame)

        result = _contact_fraction_filter(self._settlement(), voids, 50.0)

        assert result.featureCount() == 0

    @pytest.mark.integration
    def test_frame_void_contact_uses_full_perimeter_including_inner_ring(self):
        """Frame void: contact ≈ 77 % of the FULL perimeter (outer + inner ring).

        At threshold 80 % the frame must be returned. If the perimeter were
        taken from a single ring (outer 800 m → 100 %), it would be kept.
        """
        frame = self._rect(0, 0, 200, 200).difference(self._rect(70, 70, 130, 130))
        voids = self._void_layer(frame)

        result = _contact_fraction_filter(self._settlement(), voids, 80.0)

        assert result.featureCount() == 1

    @pytest.mark.integration
    def test_interior_void_never_returned(self):
        """Void (80,80)-(120,120) has no outer-boundary contact (0 %) → kept."""
        voids = self._void_layer(self._rect(80, 80, 120, 120))

        result = _contact_fraction_filter(
            self._settlement(), voids, BOUNDARY_CONTACT_THRESHOLD_PCT)

        assert result.featureCount() == 0


# ---------------------------------------------------------------------------
# TestErodeEmptyAreasIntegration — integration tests (calls processing.run)
# ---------------------------------------------------------------------------

class TestErodeEmptyAreasIntegration:
    """Integration tests for erode_empty_areas using synthetic polygon inputs."""

    CRS_ID = "EPSG:25833"

    @classmethod
    def setup_class(cls):
        """Store a frequently reused settlement geometry."""
        # 200 × 200 m settlement: used by most tests
        cls.settlement_size = 200

    def _settlement(self) -> QgsVectorLayer:
        """Return a fresh 200 × 200 m settlement polygon layer."""
        layer = make_polygon_layer(self.CRS_ID, "settlement")
        add_feature_to_layer(layer, make_square_geom(0, 0, self.settlement_size))
        return layer

    def _settlement_area(self) -> float:
        """Exact area of the standard settlement (200 × 200 = 40 000 m²)."""
        return float(self.settlement_size ** 2)

    def _buildings_layer(self, *rects) -> QgsVectorLayer:
        """Layer with one rectangular building per (left, bottom, size) tuple."""
        layer = make_polygon_layer(self.CRS_ID, "buildings")
        for left, bottom, size in rects:
            add_feature_to_layer(layer, make_square_geom(left, bottom, size))
        return layer

    # --- smoke / validity ---

    @pytest.mark.integration
    def test_returns_valid_qgsvectorlayer(self):
        """erode_empty_areas returns a non-None, valid QgsVectorLayer."""
        settlement = self._settlement()
        buildings = self._buildings_layer((10, 10, 30))

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()

    @pytest.mark.integration
    def test_result_geometries_are_geos_valid(self):
        """All output features must pass GEOS validity check.

        Setup: one 30×30 building in the center of a 200×200 settlement.
        """
        settlement = self._settlement()
        buildings = self._buildings_layer((85, 85, 30))

        result = erode_empty_areas(settlement, buildings)

        assert result.featureCount() > 0
        assert _all_geos_valid(result), \
            "One or more output geometries failed GEOS validity"

    # --- contact-fraction behaviour ---

    @pytest.mark.integration
    def test_fringe_void_with_high_boundary_contact_is_kept(self):
        """Void whose boundary runs mostly along the settlement edge is not removed.

        Setup:
          Settlement: 200 × 200 m = 40 000 m²
          Building: 20×20 at centre (90, 90); buf_dist = max(10, sqrt(400)) = 20 m
          Void: the frame surrounding the ~60×60 buffer — touches all 4 outer edges.
          Outer-boundary contact = 800 m of ~1 006 m perimeter ≈ 80 %, well above
          20 % (BOUNDARY_CONTACT_THRESHOLD_PCT) → kept.

        Expected: result area ≈ settlement area (no void eroded).
        """
        settlement = self._settlement()
        buildings = self._buildings_layer((90, 90, 20))
        expected_area = self._settlement_area()

        result = erode_empty_areas(settlement, buildings)

        result_area = _total_area(result)
        assert result_area == pytest.approx(expected_area, rel=0.05), \
            f"Expected area ≈ {expected_area:.0f} m² (void kept), got {result_area:.0f} m²"

    @pytest.mark.integration
    def test_corner_building_void_with_high_contact_kept_at_default_threshold(self):
        """Large void touching the outer boundary on ~3.5 sides is kept at 20 %.

        Setup:
          Settlement: 200 × 200 m = 40 000 m²
          Building: 10×10 at corner (5, 5); buf_dist = 10 m
          Void: everything except the corner buffer; outer-boundary contact ≈ 94 %.

        Regression for #168: the contact must be measured against the outer
        boundary, not against the remaining settlement (≈ 6 % → wrongly removed).

        Expected: result area ≈ settlement area (void kept).
        """
        settlement = self._settlement()
        buildings = self._buildings_layer((5, 5, 10))
        expected_area = self._settlement_area()

        result = erode_empty_areas(settlement, buildings)

        result_area = _total_area(result)
        assert result_area == pytest.approx(expected_area, rel=0.05), \
            f"Expected area ≈ {expected_area:.0f} m² (void kept), got {result_area:.0f} m²"

    @pytest.mark.integration
    def test_void_removed_when_contact_below_permissive_threshold(self):
        """Void whose boundary contact < contact_threshold_pct is eroded away.

        Setup:
          Settlement: 200 × 200 m = 40 000 m²
          Building: 10×10 at corner (5, 5); buf_dist = max(10, sqrt(100)) = 10 m
          Void: L-shaped frame covering most of the settlement, touching the outer
                boundary on ~3.5 of 4 sides → contact ≈ 94 % < 100 %.
          threshold = 100 % (accept any non-full-contact void for removal).

        Expected: result area < settlement area (large void eroded out).
        """
        settlement = self._settlement()
        buildings = self._buildings_layer((5, 5, 10))
        settlement_area = self._settlement_area()

        result = erode_empty_areas(
            settlement, buildings,
            contact_threshold_pct=100.0,
        )

        result_area = _total_area(result)
        assert result.featureCount() > 0, "Result must not be empty after void removal"
        assert result_area < settlement_area, \
            f"Expected result ({result_area:.0f} m²) < settlement ({settlement_area:.0f} m²)"

    # --- min_empty_area filter ---

    @pytest.mark.integration
    def test_min_empty_area_filters_all_voids_and_returns_unchanged(self):
        """Setting min_empty_area above the actual void area leaves the settlement intact.

        Setup:
          Settlement: 200 × 200 m
          Building: 20×20 at centre (90, 90) — creates a ~36 000 m² frame void.
          min_empty_area = 1 000 000 m² (larger than any void in this settlement).

        Expected: all voids filtered out → result area ≈ settlement area.
        """
        settlement = self._settlement()
        buildings = self._buildings_layer((90, 90, 20))
        expected_area = self._settlement_area()

        result = erode_empty_areas(
            settlement, buildings,
            min_empty_area=1_000_000.0,
        )

        result_area = _total_area(result)
        assert result_area == pytest.approx(expected_area, rel=0.05), \
            f"Expected area ≈ {expected_area:.0f} m² (all voids filtered), " \
            f"got {result_area:.0f} m²"

    # --- debug_mode invariant ---

    @pytest.mark.integration
    def test_debug_mode_does_not_change_result(self, tmp_path):
        """debug_mode=True produces the same feature count as debug_mode=False.

        Settlement: 200 × 200 m; one 30×30 building at corner.
        """
        settlement_a = self._settlement()
        buildings_a = self._buildings_layer((10, 10, 30))

        settlement_b = self._settlement()
        buildings_b = self._buildings_layer((10, 10, 30))

        result_normal = erode_empty_areas(settlement_a, buildings_a, debug_mode=False)
        result_debug = erode_empty_areas(
            settlement_b, buildings_b,
            debug_mode=True, workspace_path=str(tmp_path),
        )

        assert result_debug.featureCount() == result_normal.featureCount(), (
            f"debug_mode changed feature count: "
            f"normal={result_normal.featureCount()}, "
            f"debug={result_debug.featureCount()}"
        )

    # --- edge cases ---

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_null_geometry_building_is_skipped_gracefully(self):
        """Building layer with one null-geometry feature and one valid feature runs without crash.

        The null-geometry building is silently skipped in _build_buffer_layer;
        the valid building is processed normally and the result is a valid layer.
        """
        settlement = self._settlement()

        buildings = make_polygon_layer(self.CRS_ID)
        # valid building
        add_feature_to_layer(buildings, make_square_geom(80, 80, 40))
        # null-geometry building
        null_feat = QgsFeature(buildings.fields())
        buildings.dataProvider().addFeatures([null_feat])

        assert buildings.featureCount() == 2

        result = erode_empty_areas(settlement, buildings)

        assert result is not None
        assert isinstance(result, QgsVectorLayer)
        assert result.isValid()
        assert _all_geos_valid(result), "Result geometries must be GEOS-valid"
