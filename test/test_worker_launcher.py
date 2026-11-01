# -*- coding: utf-8 -*-
"""Tests for helpers/worker_launcher.py (platform-specific worker start)."""
import os
from unittest.mock import patch

import pytest

from ibtool.helpers import worker_launcher as wl


class TestDefaultWorkerCount:

    @pytest.mark.unit
    @pytest.mark.parametrize("cores, expected", [(1, 1), (2, 1), (4, 3), (5, 4), (16, 4)])
    def test_formula(self, cores, expected):
        assert wl.default_worker_count(cores) == expected

    @pytest.mark.unit
    def test_uses_detected_cores(self):
        with patch.object(wl, "physical_core_count", return_value=4):
            assert wl.default_worker_count() == 3

    @pytest.mark.unit
    def test_physical_core_count_is_positive(self):
        assert wl.physical_core_count() >= 1


class TestFindWorkerCommand:

    @pytest.mark.unit
    def test_none_on_non_windows(self, tmp_path):
        with patch.object(wl.sys, "platform", "linux"):
            assert wl.find_worker_command(str(tmp_path)) is None

    @pytest.mark.unit
    def test_windows_prefers_pythonw(self, tmp_path):
        prefix = tmp_path / "apps" / "Python312"
        prefix.mkdir(parents=True)
        (prefix / "python.exe").write_text("")
        (prefix / "pythonw.exe").write_text("")
        plugin = tmp_path / "plugin"
        (plugin / "ibtool").mkdir(parents=True)
        (plugin / "ibtool" / "partition_worker.py").write_text("")
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(prefix)):
            cmd = wl.find_worker_command(str(plugin))
        assert cmd.program == str(prefix / "pythonw.exe")
        assert cmd.arguments == ["-u", str(plugin / "ibtool" / "partition_worker.py")]

    @pytest.mark.unit
    def test_windows_without_interpreter_returns_none(self, tmp_path):
        plugin = tmp_path / "plugin"
        (plugin / "ibtool").mkdir(parents=True)
        (plugin / "ibtool" / "partition_worker.py").write_text("")
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(tmp_path / "empty")):
            assert wl.find_worker_command(str(plugin)) is None

    @pytest.mark.unit
    def test_windows_without_worker_script_returns_none(self, tmp_path):
        (tmp_path / "python.exe").write_text("")
        with patch.object(wl.sys, "platform", "win32"), \
                patch.object(wl.sys, "exec_prefix", str(tmp_path)):
            assert wl.find_worker_command(str(tmp_path / "noplugin")) is None


class TestParentAlive:

    @pytest.mark.unit
    def test_own_process_is_alive(self):
        assert wl.parent_alive(os.getpid()) is True

    @pytest.mark.unit
    def test_unused_pid_is_not_alive(self):
        assert wl.parent_alive(0x7FFFFFF0) is False
