# -*- coding: utf-8 -*-
"""Tests for helpers/partition_pipeline.py — the only partition pipeline implementation.

Structure tests with mocked tools; the equality of results on real data is
proven by full runs against the reference results (scripts/compare_results.py).
"""
from unittest.mock import MagicMock, patch

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.helpers import partition_pipeline as pp  # noqa: E402

_PARAMS = {"min_overlap_blocks": 18.0, "global_footprint_density": 0.0, "min_area": 57.0,
           "min_bdg_count": 20, "min_patch_size": 10000.0, "max_hole_size": 10000.0,
           "max_gap_size": 4900.0, "part_start": -1, "part_end": -1, "input_filter": "f.txt"}

_TOOLS = ("calc_footprint_density", "blocker", "input_hu_filter", "identify_dense_blocks",
          "calculate_mst", "mst_clustering", "add_single_bdg", "edge_catch",
          "erode_empty_areas", "gap_close", "patch_remove")


def _layers():
    return {k: MagicMock() for k in ("layer_part", "layer_hu", "layer_rn", "aux_layers_line")}


def _selection(count):
    sel = MagicMock()
    sel.featureCount.return_value = count
    return sel


class TestRunPartition:

    @pytest.mark.unit
    def test_skips_partition_with_fewer_than_10_buildings(self):
        seen = []
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=_selection(5)), \
                patch.object(pp, "logger"):
            result, count = pp.run_partition("PART_1", _layers(), MagicMock(), "/ws/", False,
                                             15.7, _PARAMS, on_selected=seen.append)
        assert (result, count) == (None, 5)
        assert seen == [5]

    @pytest.mark.unit
    def test_reports_all_phases_in_order(self):
        phases = []
        tools = {name: MagicMock() for name in _TOOLS}
        tools["patch_remove"].return_value = "RESULT"
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=_selection(100)), \
                patch.object(pp, "logger"), patch.multiple(pp, **tools):
            result, count = pp.run_partition(
                "PART_2", _layers(), MagicMock(), "/ws/", False, 15.7, _PARAMS,
                progress=lambda phase, name: phases.append((phase, name)))
        assert (result, count) == ("RESULT", 100)
        assert phases == sorted(pp.PHASES.items())

    @pytest.mark.unit
    def test_mst_failure_skips_partition(self):
        tools = {name: MagicMock() for name in _TOOLS}
        tools["calculate_mst"].return_value = None
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=_selection(100)), \
                patch.object(pp, "logger"), patch.multiple(pp, **tools):
            assert pp.run_partition("PART_3", _layers(), MagicMock(), "/ws/", False, 15.7,
                                    _PARAMS) == (None, 100)
        tools["mst_clustering"].assert_not_called()

    @pytest.mark.unit
    def test_debug_mode_uses_partition_debug_folder(self):
        tools = {name: MagicMock() for name in _TOOLS}
        with patch.object(pp, "processing"), \
                patch.object(pp, "select_and_save_by_location", return_value=_selection(100)), \
                patch.object(pp, "logger"), patch.multiple(pp, **tools):
            pp.run_partition("PART_4", _layers(), MagicMock(), "/ws/", True, 15.7, _PARAMS)
        assert tools["blocker"].call_args.kwargs["workspace_path"].replace("\\", "/") \
            == "/ws/debug/PART_PART_4"

    @pytest.mark.unit
    def test_phase_percent_covers_all_phases(self):
        assert set(pp.PHASE_PERCENT) == set(pp.PHASES)
