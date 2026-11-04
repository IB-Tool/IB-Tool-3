# -*- coding: utf-8 -*-
"""Tests for helpers/geometry_utils.nodes_detect (street end nodes by connection count).

The Python implementation must select exactly the same node points as the
former processing chain (extractspecificvertices '0, -1' -> x coordinate ->
aggregate by x -> count filter), which stays available as fallback
``_nodes_detect_processing``.
"""
from unittest.mock import patch

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis.core import Qgis
from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer, QgsWkbTypes  # noqa: E402

from ibtool.helpers import geometry_utils as gu  # noqa: E402


def _lines(wkts, geom_type="LineString"):
    layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:25833&field=id:integer", "streets", "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        if wkt is not None:
            f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


def _points(layer):
    """Sorted node coordinates (single points, multipart nodes split)."""
    out = []
    for f in layer.getFeatures():
        geom = f.geometry()
        for part in geom.constParts():
            out.append((part.x(), part.y()))
    return sorted(out)


CASES = {
    "t_junction_and_dead_ends": [
        "LineString (0 0, 10 0)", "LineString (10 0, 20 0)", "LineString (10 0, 10 10)"],
    "multilinestring_uses_first_and_last_vertex_of_whole_geometry": [
        "MultiLineString ((0 0, 5 0), (7 3, 9 9))", "LineString (9 9, 9 20)"],
    "closed_line": ["LineString (0 0, 10 0, 10 10, 0 0)", "LineString (30 0, 40 5)"],
    "different_nodes_with_same_x_count_together": [
        "LineString (5 0, 5 10)", "LineString (100 50, 5 80)", "LineString (100 50, 200 50)"],
    "null_geometry_is_ignored": [None, "LineString (0 0, 1 1)", "LineString (1 1, 2 0)"],
    "x_differs_in_11th_decimal_stays_separate": [
        "LineString (100.00000000001 0, 150 30)", "LineString (100.00000000002 50, 170 80)",
        "LineString (300.00000000006 0, 310 9)", "LineString (300.00000000004 40, 320 5)"],
    "fractional_coordinates": [
        "LineString (385432.123456789 5818123.987654321, 385440.5 5818130.25)",
        "LineString (385440.5 5818130.25, 385450.000000001 5818100)"],
}


class TestNodesDetect:

    @pytest.mark.integration
    @pytest.mark.parametrize("name", sorted(CASES))
    @pytest.mark.parametrize("count", [1, 2])
    def test_same_nodes_as_processing_chain(self, name, count):
        geom_type = "MultiLineString" if name.startswith("multi") else "LineString"
        layer = _lines(CASES[name], geom_type)
        expected = _points(gu._nodes_detect_processing(layer, count))
        assert _points(gu.nodes_detect(layer, count)) == expected

    @pytest.mark.integration
    def test_dead_end_nodes_of_t_junction(self):
        """Nodes are grouped by x only (kept from the original ArcPy port):
        (10 10) shares x = 10 with the junction (10 0), so it is not a dead end."""
        layer = _lines(CASES["t_junction_and_dead_ends"])
        assert _points(gu.nodes_detect(layer, 1)) == [(0, 0), (20, 0)]

    @pytest.mark.integration
    def test_output_is_point_layer_in_input_crs(self):
        layer = _lines(CASES["t_junction_and_dead_ends"])
        nodes = gu.nodes_detect(layer, 1)
        assert QgsWkbTypes.geometryType(nodes.wkbType()) == Qgis.GeometryType.Point
        assert nodes.crs().authid() == "EPSG:25833"

    @pytest.mark.integration
    def test_does_not_run_processing(self):
        layer = _lines(CASES["t_junction_and_dead_ends"])
        with patch.object(gu.processing, "run", side_effect=AssertionError("processing")):
            gu.nodes_detect(layer, 1)

    @pytest.mark.integration
    def test_falls_back_to_processing_chain_on_error(self):
        layer = _lines(CASES["t_junction_and_dead_ends"])
        with patch.object(gu, "_count_end_nodes", side_effect=RuntimeError("boom")):
            nodes = gu.nodes_detect(layer, 1)
        assert _points(nodes) == [(0, 0), (20, 0)]
