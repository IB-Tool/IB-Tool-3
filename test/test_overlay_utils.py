# -*- coding: utf-8 -*-
"""Tests for helpers/overlay_utils.py — QgsGeometry equivalents of QGIS algorithms.

Every function must reproduce the processing algorithm it replaces (same
geometries, attributes and order); each test compares directly against
``processing.run`` on small synthetic layers. The equivalence on real data is
covered by ``scripts/edge_catch_harness.py`` (1,927 sample rectangles) and full
pipeline runs against the reference results.
"""
from unittest.mock import patch

import pytest
from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer, Qgis

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis import processing  # noqa: E402

from ibtool.helpers.overlay_utils import (  # noqa: E402
    GeometryOperationError,
    checked,
    extract_intersecting,
    intersection_with,
    make_valid_polygon,
    polygonize_lines,
)


def _layer(geom_type, wkts, fields="", name="l"):
    layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:25833{fields}", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        if layer.fields().count():
            f.setAttributes([i + 1, f"n{i + 1}"][:layer.fields().count()])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


def _rows(layer):
    return [(f.geometry().asWkt(17), f.attributes()) for f in layer.getFeatures()]


class TestChecked:

    @pytest.mark.unit
    def test_valid_geometry_is_returned(self):
        g = QgsGeometry.fromWkt("Point (1 2)")
        assert checked(g, "op") is g

    @pytest.mark.unit
    def test_empty_result_without_error_is_returned(self):
        g = QgsGeometry()
        assert checked(g, "op").isNull()

    @pytest.mark.unit
    def test_null_result_with_error_raises(self):
        g = QgsGeometry.fromWkt("Polygon ((0 0, 1 0, 1 1, 0 0))")
        failed = g.intersection(QgsGeometry())     # null input -> error set on result
        if not (failed.isNull() and failed.lastError()):
            pytest.skip("this QGIS version reports no error for a null operand")
        with pytest.raises(GeometryOperationError):
            checked(failed, "intersection")


class TestMakeValidPolygon:
    """make_valid_polygon == native:fixgeometries (METHOD 1) on a polygon layer."""

    @pytest.mark.integration
    @pytest.mark.parametrize("wkt", [
        "Polygon ((0 0, 10 0, 10 10, 0 10, 0 0))",                         # valid
        "Polygon ((0 0, 10 10, 10 0, 0 10, 0 0))",                         # bow-tie
        "Polygon ((0 0, 10 0, 10 0, 10 10, 10 10, 0 10, 0 10, 0 0))",      # duplicate vertices
        "Polygon ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 12 2, 12 8, 2 8, 2 2))",  # hole outside shell
    ])
    def test_identical_to_fixgeometries(self, wkt):
        layer = _layer("Polygon", [wkt])
        expected = processing.run("native:fixgeometries", {
            "INPUT": layer, "METHOD": 1, "OUTPUT": "memory:"})["OUTPUT"]
        expected_wkt = [f.geometry().asWkt(17) for f in expected.getFeatures()]
        result = make_valid_polygon(QgsGeometry.fromWkt(wkt))
        assert [result.asWkt(17)] == expected_wkt


class TestExtractIntersecting:
    """extract_intersecting == native:extractbylocation (intersects), incl. order."""

    @staticmethod
    def _expected(target, intersect_layer):
        out = processing.run("native:extractbylocation", {
            "INPUT": target, "PREDICATE": [0], "INTERSECT": intersect_layer,
            "OUTPUT": "memory:"})["OUTPUT"]
        return _rows(out)

    @pytest.mark.integration
    def test_many_targets_few_intersect_geometries(self):
        target = _layer("Polygon", [
            f"Polygon (({x} 0, {x + 8} 0, {x + 8} 8, {x} 8, {x} 0))" for x in range(0, 200, 10)],
            "&field=id:integer&field=name:string")
        probes = ["Polygon ((95 -5, 135 -5, 135 20, 95 20, 95 -5))",
                  "Polygon ((-5 -5, 25 -5, 25 20, -5 20, -5 -5))"]
        intersect_layer = _layer("Polygon", probes)
        got = [(f.geometry().asWkt(17), f.attributes())
               for f in extract_intersecting(target, [QgsGeometry.fromWkt(w) for w in probes])]
        assert got == self._expected(target, intersect_layer)

    @pytest.mark.integration
    def test_few_targets_many_intersect_geometries(self):
        target = _layer("Polygon", ["Polygon ((0 0, 50 0, 50 50, 0 50, 0 0))",
                                    "Polygon ((100 0, 150 0, 150 50, 100 50, 100 0))"],
                        "&field=id:integer&field=name:string")
        probes = [f"Point ({x} 25)" for x in (10, 20, 120, 300, 30)]
        intersect_layer = _layer("Point", probes)
        got = [(f.geometry().asWkt(17), f.attributes())
               for f in extract_intersecting(target, [QgsGeometry.fromWkt(w) for w in probes])]
        assert got == self._expected(target, intersect_layer)


class TestPolygonizeLines:
    """polygonize_lines == extendlines -> fixgeometries -> polygonize."""

    @pytest.mark.integration
    def test_identical_to_processing_chain(self):
        wkts = ["LineString (0 0, 100 0)", "LineString (100 0, 100 100)",
                "LineString (100 100, 0 100)", "LineString (0 100, 0 0)",
                "LineString (50 -10, 50 110)", "LineString (0 50, 49.5 50)",
                "LineString (20 20, 30 30, 20 20)"]
        layer = _layer("LineString", wkts)
        ext = processing.run("native:extendlines", {"INPUT": layer, "START_DISTANCE": 1,
                                                    "END_DISTANCE": 1, "OUTPUT": "memory:"})["OUTPUT"]
        fixed = processing.run("native:fixgeometries", {"INPUT": ext, "METHOD": 1,
                                                        "OUTPUT": "memory:"})["OUTPUT"]
        polys = processing.run("native:polygonize", {"INPUT": fixed, "KEEP_FIELDS": False,
                                                     "OUTPUT": "memory:"})["OUTPUT"]
        expected = [f.geometry().asWkt(17) for f in polys.getFeatures()]

        got = [g.asWkt(17) for g in polygonize_lines([QgsGeometry.fromWkt(w) for w in wkts], 1)]
        assert got == expected
        assert len(got) >= 3

    @pytest.mark.unit
    def test_no_lines_gives_no_polygons(self):
        assert polygonize_lines([], 1) == []


class TestIntersectionWith:
    """intersection_with == native:intersection (no grid) for one input feature.

    Same features (geometry + attributes). The ORDER of native:intersection is
    not defined: it fetches the overlay candidates via ``setFilterFids`` on a
    hash set of IDs (here block 4 came before block 1), which is also why the
    order of EdgeCatch results varied between QGIS processes. intersection_with
    returns the overlay layer order, deterministically.
    """

    @pytest.mark.integration
    def test_identical_to_native_intersection(self):
        polygon = "Polygon ((0 0, 100 0, 100 100, 0 100, 0 0))"
        blocks = ["Polygon ((50 50, 150 50, 150 150, 50 150, 50 50))",       # overlap
                  "Polygon ((200 0, 250 0, 250 50, 200 50, 200 0))",         # disjoint
                  "Polygon ((100 0, 120 0, 120 100, 100 100, 100 0))",       # edge only
                  "Polygon ((-10 -10, 30 -10, 30 30, -10 30, -10 -10))"]     # overlap
        input_layer = _layer("Polygon", [polygon])
        block_layer = _layer("Polygon", blocks, "&field=id:integer&field=name:string")
        expected = processing.run("native:intersection", {
            "INPUT": input_layer, "OVERLAY": block_layer, "INPUT_FIELDS": [], "OVERLAY_FIELDS": [],
            "OVERLAY_FIELDS_PREFIX": "", "OUTPUT": "memory:", "GRID_SIZE": None})["OUTPUT"]
        got = [(g.asWkt(17), f.attributes())
               for g, f in intersection_with(QgsGeometry.fromWkt(polygon), list(block_layer.getFeatures()))]
        assert sorted(map(str, got)) == sorted(map(str, _rows(expected)))
        assert all(QgsGeometry.fromWkt(w).wkbType() == Qgis.WkbType.MultiPolygon for w, _ in got)

    @pytest.mark.unit
    def test_result_follows_overlay_order(self):
        polygon = QgsGeometry.fromWkt("Polygon ((0 0, 100 0, 100 100, 0 100, 0 0))")
        blocks = _layer("Polygon", ["Polygon ((50 50, 150 50, 150 150, 50 150, 50 50))",
                                    "Polygon ((-10 -10, 30 -10, 30 30, -10 30, -10 -10))"],
                        "&field=id:integer&field=name:string")
        ids = [f["id"] for _g, f in intersection_with(polygon, list(blocks.getFeatures()))]
        assert ids == [1, 2]
