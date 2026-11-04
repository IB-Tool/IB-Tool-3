# -*- coding: utf-8 -*-
"""Tests for helpers/worker_pool.py with a fake worker (runs on every platform)."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from qgis.PyQt.QtCore import QEventLoop, QTimer  # noqa: E402

from ibtool.helpers.worker_launcher import WorkerCommand  # noqa: E402
from ibtool.helpers.worker_pool import WorkerPool  # noqa: E402

FAKE = WorkerCommand(sys.executable, ["-u", str(Path(__file__).with_name("fake_worker.py"))])
DIES_AT_START = WorkerCommand(sys.executable, ["-c", "import sys; sys.exit(5)"])
NOT_STARTABLE = WorkerCommand(str(Path(__file__).with_name("no_such_program.exe")), [])


def _run(pool, partitions, timeout_ms=30000):
    done, logs, finished = [], [], []
    pool.partition_done.connect(done.append)
    pool.log.connect(lambda level, msg: logs.append(msg))
    loop = QEventLoop()
    pool.finished.connect(lambda: finished.append(True))
    pool.finished.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    pool.run(partitions)
    if not finished:
        loop.exec()
    assert finished, "pool never emitted finished"
    return done, logs


class TestWorkerPool:

    @pytest.mark.integration
    def test_all_partitions_done_and_noise_ignored(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, logs = _run(pool, ["a", "b", "c", "d"])
        assert sorted(d["partition"] for d in done) == ["a", "b", "c", "d"]
        assert any("[a] did a" in m for m in logs)
        assert pool.recompute == []
        assert pool.process_count() == 0

    @pytest.mark.integration
    def test_largest_first_order_is_kept(self):
        pool = WorkerPool(FAKE, 1, {})
        assert pool.selftest()
        done, _ = _run(pool, ["big", "mid", "small"])
        assert [d["partition"] for d in done] == ["big", "mid", "small"]

    @pytest.mark.integration
    def test_crash_and_error_go_to_recompute_list(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, _ = _run(pool, ["a", "crash1", "error1", "b"])
        assert sorted(d["partition"] for d in done) == ["a", "b"]
        assert sorted(pool.recompute) == ["crash1", "error1"]

    @pytest.mark.integration
    def test_selftest_timeout_falls_back(self):
        with patch.dict(os.environ, {"FAKE_NO_READY": "1"}):
            pool = WorkerPool(FAKE, 2, {}, ready_timeout_s=1.0)
            assert pool.selftest() is False
        assert pool.process_count() == 0

    @pytest.mark.integration
    def test_selftest_with_unstartable_program_fails_fast(self):
        pool = WorkerPool(NOT_STARTABLE, 2, {}, ready_timeout_s=30.0)
        started = time.monotonic()
        assert pool.selftest() is False
        assert time.monotonic() - started < 10

    @pytest.mark.integration
    def test_cancel_stops_all_workers(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        QTimer.singleShot(300, pool.cancel)
        done, _ = _run(pool, ["slow1", "slow2", "slow3", "slow4"], timeout_ms=10000)
        assert len(done) < 4
        assert pool.process_count() == 0

    @pytest.mark.integration
    def test_majority_crash_stops_pool(self):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        done, _ = _run(pool, ["crash1", "crash2", "crash3", "a", "b"])
        assert set(pool.recompute) >= {"crash1", "crash2"}
        assert {d["partition"] for d in done} | set(pool.recompute) == \
            {"crash1", "crash2", "crash3", "a", "b"}

    @pytest.mark.integration
    @pytest.mark.parametrize("broken", [DIES_AT_START, NOT_STARTABLE], ids=["dies", "unstartable"])
    def test_no_live_worker_left_moves_queue_to_recompute(self, broken):
        pool = WorkerPool(FAKE, 2, {})
        assert pool.selftest()
        pool._command = broken          # every further worker fails before 'ready'
        done, _ = _run(pool, ["crash1", "a", "b", "c"], timeout_ms=20000)
        assert {d["partition"] for d in done} | set(pool.recompute) == {"crash1", "a", "b", "c"}
        assert "crash1" in pool.recompute
        assert pool.process_count() == 0
