# -*- coding: utf-8 -*-
"""Tests for helpers/run_manifest.py (ibtool_run.json)."""
import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from ibtool.helpers import run_manifest as rm  # noqa: E402


def _inputs(tmp_path, hu_content="hu"):
    files = {}
    for key, content in (("hu", hu_content), ("rn", "rn"), ("part", "part"), ("aux", "aux"),
                         ("filter", "filter")):
        p = tmp_path / f"in_{key}.dat"     # not "aux.dat": AUX is a reserved device on Windows
        p.write_text(content)
        files[key] = str(p)
    return files


def _manifest(tmp_path, **kw):
    if "inputs" not in kw:
        kw["inputs"] = _inputs(tmp_path)     # only when not given: rewrites the input files
    args = dict(params={"min_area": 57.0, "part_list": "#"},
                crs_authid="EPSG:25833", plugin_version="0.2.5", qgis_version="3.44.15",
                worker_count=3)
    args.update(kw)
    return rm.build_manifest(**args)


class TestManifest:

    @pytest.mark.unit
    def test_write_read_round_trip_and_atomic(self, tmp_path):
        m = _manifest(tmp_path)
        rm.write_manifest(str(tmp_path), m, "running")
        stored = rm.read_manifest(str(tmp_path))
        assert stored["status"] == "running" and stored["inputs"]["hu"]["checksum"]
        assert not list(tmp_path.glob("*.tmp"))

    @pytest.mark.unit
    def test_rewrite_keeps_created_timestamp(self, tmp_path):
        stored_created = "2000-01-01T00:00:00"
        rm.write_manifest(str(tmp_path), dict(_manifest(tmp_path), created=stored_created),
                          "running")
        rm.write_manifest(str(tmp_path), _manifest(tmp_path), "finished")   # freshly built
        again = rm.read_manifest(str(tmp_path))
        assert again["created"] == stored_created and again["status"] == "finished"

    @pytest.mark.unit
    def test_identical_runs_have_no_differences(self, tmp_path):
        assert rm.compare_manifests(_manifest(tmp_path), _manifest(tmp_path)) == []

    @pytest.mark.unit
    def test_worker_count_does_not_invalidate_resume(self, tmp_path):
        assert rm.compare_manifests(_manifest(tmp_path, worker_count=3),
                                    _manifest(tmp_path, worker_count=1)) == []

    @pytest.mark.unit
    def test_changed_input_param_and_qgis_version_are_reported(self, tmp_path):
        old = _manifest(tmp_path)
        new = _manifest(tmp_path, inputs=_inputs(tmp_path, hu_content="changed"),
                        params={"min_area": 60.0, "part_list": "#"}, qgis_version="3.40.0")
        diffs = rm.compare_manifests(old, new)
        assert any("Gebäude" in d for d in diffs)
        assert any("min_area" in d for d in diffs)
        assert any("3.44.15 → 3.40.0" in d for d in diffs)

    @pytest.mark.unit
    def test_moved_input_with_same_content_is_ok(self, tmp_path):
        old = _manifest(tmp_path)
        moved = tmp_path / "elsewhere"
        moved.mkdir()
        (moved / "in_hu.dat").write_text("hu")
        new_inputs = dict(_inputs(tmp_path), hu=str(moved / "in_hu.dat"))
        assert rm.compare_manifests(old, _manifest(tmp_path, inputs=new_inputs)) == []

    @pytest.mark.unit
    def test_missing_or_broken_manifest_reads_none(self, tmp_path):
        assert rm.read_manifest(str(tmp_path)) is None
        (tmp_path / rm.MANIFEST_NAME).write_text("{broken")
        assert rm.read_manifest(str(tmp_path)) is None

    @pytest.mark.unit
    def test_ui_settings(self, tmp_path):
        s = rm.manifest_to_ui_settings(_manifest(tmp_path))
        assert s["inputs"]["hu"].endswith("in_hu.dat") and s["params"]["min_area"] == 57.0
