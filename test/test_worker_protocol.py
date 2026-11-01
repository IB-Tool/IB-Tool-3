# -*- coding: utf-8 -*-
"""Tests for helpers/worker_protocol.py (JSON-lines protocol plugin <-> worker)."""
import pytest

from ibtool.helpers import worker_protocol as wp


class TestProtocol:

    @pytest.mark.unit
    def test_event_round_trip(self):
        line = wp.encode(wp.done_event("PART_64", 7139, "parts/PART_64.gpkg", 23, 59.7))
        assert line.startswith(wp.PREFIX) and line.endswith("\n")
        assert wp.parse_line(line) == {"type": "done", "partition": "PART_64", "buildings": 7139,
                                       "result": "parts/PART_64.gpkg", "features": 23,
                                       "seconds": 59.7}

    @pytest.mark.unit
    @pytest.mark.parametrize("line", ["", "QGIS: warning foo\n", "IBTOOL not json\n",
                                      "IBTOOL [1, 2]\n", "IBTOOL {\"no_type\": 1}\n"])
    def test_foreign_or_broken_lines_are_ignored(self, line):
        assert wp.parse_line(line) is None

    @pytest.mark.unit
    def test_unicode_and_paths_survive(self):
        msg = wp.log_event("INFO", "Pfad C:\\Daten\\IB Läufe\\Teil: Nord")
        assert wp.parse_line(wp.encode(msg)) == msg

    @pytest.mark.unit
    def test_command_encoding(self):
        raw = wp.encode_command(wp.run_message("PART_7"))
        assert raw == b'{"type": "run", "partition": "PART_7"}\n'

    @pytest.mark.unit
    def test_one_line_per_message(self):
        msg = wp.error_event("PART_1", "boom", "Traceback...\nline 2\n")
        assert wp.encode(msg).count("\n") == 1

    @pytest.mark.unit
    def test_builders(self):
        assert wp.init_message(a=1)["type"] == "init"
        assert wp.exit_message() == {"type": "exit"}
        assert wp.ready_event() == {"type": "ready"}
        assert wp.progress_event("P", 3, "Apply Filter") == {
            "type": "progress", "partition": "P", "phase": 3, "phase_name": "Apply Filter"}
