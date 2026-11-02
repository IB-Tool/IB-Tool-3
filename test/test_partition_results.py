# -*- coding: utf-8 -*-
"""Tests for helpers/partition_results.py (part files, finish log, resume, final merge)."""
import os
from unittest.mock import patch

import pytest
from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsVectorLayer

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.helpers import partition_results as pr  # noqa: E402
from ibtool.helpers.geometry_utils import create_empty_layer  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:25833")


def _layer(xs):
    layer = QgsVectorLayer("MultiPolygon?crs=EPSG:25833&field=Area:double", "r", "memory")
    feats = []
    for x in xs:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(
            f"MultiPolygon ((({x} 0, {x + 10} 0, {x + 10} 10, {x} 10, {x} 0)))"))
        f.setAttributes([100.0])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


class TestPartFiles:

    @pytest.mark.unit
    def test_part_file_name_is_sanitized_and_unique(self):
        assert pr.part_file_name("PART_64") == "PART_64.gpkg"
        a, b = pr.part_file_name("Teil: Nord"), pr.part_file_name("Teil/ Nord")
        assert a != b and a.endswith(".gpkg")
        assert not any(c in a for c in '<>:"/\\|?*')
        assert pr.part_file_name('"A"') != pr.part_file_name("A")

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["AUX", "con", "Nul", "COM1", "lpt9", "PRN"])
    def test_windows_reserved_device_names_are_avoided(self, name):
        stem = pr.part_file_name(name)[:-len(".gpkg")]
        assert stem.upper() not in {"AUX", "CON", "NUL", "PRN", "COM1", "LPT9"}
        assert pr.part_file_name(name) != pr.part_file_name(name.swapcase())

    @pytest.mark.unit
    def test_names_differing_only_in_case_get_distinct_files(self):
        names = ["PART_1", "part_1", "Part_1"]
        files = {pr.part_file_name(n).lower() for n in names}     # Windows ignores case
        assert len(files) == 3

    @pytest.mark.integration
    def test_write_is_atomic_and_counts_features(self, tmp_path):
        rel, count = pr.write_part_result(_layer([0, 20, 40]), "PART_1", str(tmp_path))
        assert rel == "parts/PART_1.gpkg" and count == 3
        assert (tmp_path / "parts" / "PART_1.gpkg").is_file()
        assert not list((tmp_path / "parts").glob("*.tmp.gpkg"))

    @pytest.mark.integration
    def test_duplicate_fid_attribute_is_written_and_kept(self, tmp_path):
        layer = QgsVectorLayer("MultiPolygon?crs=EPSG:25833&field=fid:integer&field=Area:double",
                               "r", "memory")
        feats = []
        for x in (0, 20):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(
                f"MultiPolygon ((({x} 0, {x + 10} 0, {x + 10} 10, {x} 10, {x} 0)))"))
            f.setAttributes([1, 100.0])                       # same fid twice (merge result)
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        rel, count = pr.write_part_result(layer, "P1", str(tmp_path))
        assert count == 2
        base = create_empty_layer("global_merge_layer", "Polygon", CRS.authid())
        merged = pr.merge_results(str(tmp_path), ["P1"], {"P1": pr.FinishedPart("P1", rel, 2)},
                                  base, CRS)
        names = [f.name() for f in merged.fields()]
        assert "fid" in names and "Area" in names and "gpkg_fid" not in names
        assert sorted(f["fid"] for f in merged.getFeatures()) == [1, 1]

    @pytest.mark.integration
    def test_rewrite_replaces_existing_part(self, tmp_path):
        pr.write_part_result(_layer([0, 20]), "PART_1", str(tmp_path))
        rel, count = pr.write_part_result(_layer([0]), "PART_1", str(tmp_path))
        layer = QgsVectorLayer(f"{tmp_path / rel}|layername=result", "r", "ogr")
        assert count == 1 and layer.featureCount() == 1

    @pytest.mark.integration
    def test_failed_part_write_leaves_no_finish_line(self, tmp_path):
        log = tmp_path / "fin.txt"
        with patch.object(pr.os, "replace", side_effect=OSError("locked")):
            with pytest.raises(OSError):
                pr.write_part_result(_layer([0]), "PART_1", str(tmp_path))
        assert not log.exists()
        assert not (tmp_path / "parts" / "PART_1.gpkg").exists()
        assert not list((tmp_path / "parts").glob("*.tmp.gpkg"))

    @pytest.mark.integration
    def test_cleanup_removes_temporary_files(self, tmp_path):
        parts = tmp_path / "parts"
        parts.mkdir()
        (parts / "PART_1.tmp.gpkg").write_text("x")
        (parts / "PART_2.gpkg").write_text("x")
        pr.cleanup_temporary(str(tmp_path))
        assert sorted(p.name for p in parts.iterdir()) == ["PART_2.gpkg"]


class TestFinishLog:

    @pytest.mark.unit
    def test_round_trip_new_format(self, tmp_path):
        log = str(tmp_path / "fin.txt")
        pr.append_finished(log, pr.FinishedPart("PART_64", "parts/PART_64.gpkg", 23))
        pr.append_finished(log, pr.FinishedPart("PART_9", None, None))
        assert pr.read_finished(log) == {
            "PART_64": pr.FinishedPart("PART_64", "parts/PART_64.gpkg", 23),
            "PART_9": pr.FinishedPart("PART_9", None, None)}

    @pytest.mark.unit
    def test_old_format_and_truncated_line(self, tmp_path):
        log = tmp_path / "fin.txt"
        log.write_text("\nPART_1\nPART_2\nPART_3\tparts/PART_3.gp", encoding="utf-8")
        got = pr.read_finished(str(log))
        assert set(got) == {"PART_1", "PART_2"}
        assert got["PART_1"] == pr.FinishedPart("PART_1", pr.OLD_FORMAT, None)

    @pytest.mark.unit
    def test_old_format_last_line_without_newline_is_complete(self, tmp_path):
        log = tmp_path / "fin.txt"
        log.write_text("\nPART_1\nPART_2", encoding="utf-8")       # as written by <= 0.2.4
        assert set(pr.read_finished(str(log))) == {"PART_1", "PART_2"}

    @pytest.mark.unit
    def test_append_to_old_format_log_starts_new_line(self, tmp_path):
        """Regression: the first new line was glued onto the last old name ("BC")."""
        log = tmp_path / "fin.txt"
        log.write_text("\nA\nB", encoding="utf-8")                 # as written by <= 0.2.4
        pr.append_finished(str(log), pr.FinishedPart("C", "parts/C.gpkg", 5))
        pr.append_finished(str(log), pr.FinishedPart("D", None, None))
        assert pr.read_finished(str(log)) == {
            "A": pr.FinishedPart("A", pr.OLD_FORMAT, None),
            "B": pr.FinishedPart("B", pr.OLD_FORMAT, None),
            "C": pr.FinishedPart("C", "parts/C.gpkg", 5),
            "D": pr.FinishedPart("D", None, None)}

    @pytest.mark.unit
    def test_append_after_truncated_line_keeps_it_ignored(self, tmp_path):
        log = tmp_path / "fin.txt"
        log.write_text("A\tparts/A.gpkg\t3\nB\tparts/B.gp", encoding="utf-8")  # crash
        pr.append_finished(str(log), pr.FinishedPart("C", None, None))
        assert set(pr.read_finished(str(log))) == {"A", "C"}

    @pytest.mark.unit
    def test_append_to_empty_log_adds_no_blank_line(self, tmp_path):
        log = tmp_path / "fin.txt"
        log.write_text("", encoding="utf-8")
        pr.append_finished(str(log), pr.FinishedPart("A", None, None))
        assert log.read_text(encoding="utf-8") == "A\tskipped\n"

    @pytest.mark.unit
    def test_missing_log_is_empty(self, tmp_path):
        assert pr.read_finished(str(tmp_path / "none.txt")) == {}


class TestValidateAndMerge:

    @pytest.mark.integration
    def test_validate_detects_missing_and_wrong_count(self, tmp_path):
        ok_rel, n = pr.write_part_result(_layer([0, 20]), "A", str(tmp_path))
        bad_rel, _ = pr.write_part_result(_layer([0]), "B", str(tmp_path))
        finished = {"A": pr.FinishedPart("A", ok_rel, n), "B": pr.FinishedPart("B", bad_rel, 5),
                    "C": pr.FinishedPart("C", "parts/C.gpkg", 1),
                    "S": pr.FinishedPart("S", None, None),
                    "O": pr.FinishedPart("O", pr.OLD_FORMAT, None)}
        valid, recompute = pr.validate_finished(str(tmp_path), finished)
        assert set(valid) == {"A", "S", "O"} and sorted(recompute) == ["B", "C"]

    @pytest.mark.integration
    def test_merge_order_equals_former_incremental_merge(self, tmp_path):
        finished = {}
        for name, x in (("P1", 0), ("P2", 100), ("P3", 200)):
            rel, n = pr.write_part_result(_layer([x]), name, str(tmp_path))
            finished[name] = pr.FinishedPart(name, rel, n)
        finished["P0"] = pr.FinishedPart("P0", None, None)
        base = create_empty_layer("global_merge_layer", "Polygon", CRS.authid())
        merged = pr.merge_results(str(tmp_path), ["P0", "P1", "P2", "P3"], finished, base, CRS)
        xs = [round(f.geometry().boundingBox().xMinimum()) for f in merged.getFeatures()]
        assert xs == [200, 100, 0]                 # last partition first, as before
        assert "fid" not in [f.name().lower() for f in merged.fields()]

    @pytest.mark.integration
    def test_merged_result_can_be_written_to_geopackage(self, tmp_path):
        finished = {}
        for name, x in (("P1", 0), ("P2", 100)):
            rel, n = pr.write_part_result(_layer([x, x + 30]), name, str(tmp_path))
            finished[name] = pr.FinishedPart(name, rel, n)
        base = create_empty_layer("global_merge_layer", "Polygon", CRS.authid())
        merged = pr.merge_results(str(tmp_path), ["P1", "P2"], finished, base, CRS)
        from ibtool.helpers.system_utils import save_temp_layer_to_gpkg
        out = save_temp_layer_to_gpkg(merged, "final", str(tmp_path) + "/")
        assert out and QgsVectorLayer(out, "f", "ogr").featureCount() == 4


class TestEstimateBuildings:

    @pytest.mark.integration
    def test_counts_buildings_per_partition_bbox(self):
        hu = _layer([0, 20, 200])                          # two left, one right
        part = QgsVectorLayer("Polygon?crs=EPSG:25833&field=NAME:string", "p", "memory")
        feats = []
        for name, wkt in (("A", "Polygon ((-5 -5, 40 -5, 40 15, -5 15, -5 -5))"),
                          ("B", "Polygon ((150 -5, 250 -5, 250 15, 150 15, 150 -5))"),
                          ("C", "Polygon ((500 500, 510 500, 510 510, 500 500))")):
            f = QgsFeature(part.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([name])
            feats.append(f)
        part.dataProvider().addFeatures(feats)
        assert pr.estimate_buildings(hu, part, ["A", "B", "C"]) == {"A": 2, "B": 1, "C": 0}
        assert pr.estimate_buildings(hu, part, ["B"]) == {"B": 1}


class TestPlanning:

    @pytest.mark.unit
    def test_plan_recomputes_invalid_results_outside_selection(self):
        valid = {"A": pr.FinishedPart("A", "parts/A.gpkg", 1)}
        work_list, todo = pr.plan_partitions(["A", "B"], valid, ["X", "B"])
        assert work_list == ["A", "B", "X"]
        assert todo == ["B", "X"]

    @pytest.mark.unit
    def test_plan_without_resume(self):
        assert pr.plan_partitions(["A", "B"], {}, []) == (["A", "B"], ["A", "B"])

    @pytest.mark.unit
    def test_merge_order_earlier_batches_first_each_once(self):
        finished = {name: pr.FinishedPart(name, None, None) for name in ("E1", "B", "E2", "A")}
        assert pr.merge_order(finished, ["A", "B", "A"]) == ["E1", "E2", "A", "B"]

    @pytest.mark.integration
    def test_merge_skips_unreadable_part_file(self, tmp_path):
        rel, n = pr.write_part_result(_layer([0]), "A", str(tmp_path))
        finished = {"A": pr.FinishedPart("A", rel, n),
                    "X": pr.FinishedPart("X", "parts/X.gpkg", 1)}      # file missing
        base = create_empty_layer("global_merge_layer", "Polygon", CRS.authid())
        merged = pr.merge_results(str(tmp_path), ["X", "A"], finished, base, CRS)
        assert merged.isValid() and merged.featureCount() == 1
