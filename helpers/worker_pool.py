# -*- coding: utf-8 -*-
"""Worker pool: N QProcess workers computing partitions (plugin side).

Runs in the QGIS main thread; everything is signal-driven, so the dialog stays
responsive. Crashed or failing partitions are collected in ``recompute`` and
processed by the plugin in its own process afterwards (same behaviour as the
sequential path). If more than half of the started workers crashed, no new
workers are started and the remaining partitions go to ``recompute``.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
from collections import deque

from qgis.PyQt.QtCore import QEventLoop, QObject, QProcess, QTimer, pyqtSignal

from . import worker_protocol as wp

KILL_GRACE_MS = 2000


class _Worker:  # pylint: disable=too-few-public-methods
    """State of one worker process."""

    def __init__(self, ident, process):
        self.ident = ident
        self.process = process
        self.buffer = b""
        self.ready = False
        self.partition = None
        self.exited = False
        self.stderr = deque(maxlen=50)


class WorkerPool(QObject):  # pylint: disable=too-many-instance-attributes
    """Fixed pool of worker processes; see the module docstring."""

    progress = pyqtSignal(str, int, str)
    log = pyqtSignal(str, str)
    partition_done = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, command, worker_count, init_fields, ready_timeout_s=60.0, parent=None):
        super().__init__(parent)
        self._command = command
        self._count = max(1, worker_count)
        self._init = wp.init_message(**init_fields)
        self._timeout_ms = int(ready_timeout_s * 1000)
        self._workers = {}
        self._queue = deque()
        self._next_id = 0
        self._crashes = 0
        self._started = 0
        self._stopping = False
        self._run_started = False
        self._ready_waiter = None
        self.recompute = []

    # -- lifecycle -------------------------------------------------------------
    def process_count(self):
        """Number of worker processes still running."""
        return sum(1 for w in self._workers.values()
                   if w.process.state() != QProcess.ProcessState.NotRunning)

    @property
    def size(self):
        """Configured number of worker processes."""
        return self._count

    @property
    def running(self):
        """Worker id -> partition currently processed."""
        return {w.ident: w.partition for w in self._workers.values() if w.partition}

    def selftest(self):
        """Start one worker and wait for ``ready``; on failure kill everything."""
        worker = self._start_worker()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        worker.process.finished.connect(loop.quit)
        self._ready_waiter = loop
        timer.start(self._timeout_ms)
        if not worker.ready and not worker.exited:   # FailedToStart is reported in start()
            loop.exec()
        self._ready_waiter = None
        if worker.ready:
            return True
        self._kill_all()
        return False

    def run(self, partitions):
        """Process *partitions* (already sorted, largest first); emits ``finished``."""
        self._queue.extend(partitions)
        self._run_started = True
        while len(self._workers) < min(self._count, len(self._queue)) and not self._stopping:
            self._start_worker()
        for worker in list(self._workers.values()):
            self._dispatch(worker)
        self._check_finished()

    def cancel(self):
        """Stop all workers (terminate, kill after the grace period) and emit ``finished``."""
        self._stopping = True
        self._queue.clear()
        self._kill_all()
        self.finished.emit()

    def stderr_tail(self, n=50):
        """Last *n* stderr lines of all workers (for the error log)."""
        lines = []
        for worker in self._workers.values():
            lines.extend(list(worker.stderr)[-n:])
        return lines[-n:]

    # -- internals -------------------------------------------------------------
    def _start_worker(self):
        process = QProcess(self)
        ident = f"w{self._next_id}"
        self._next_id += 1
        worker = _Worker(ident, process)
        self._workers[ident] = worker
        process.readyReadStandardOutput.connect(lambda w=worker: self._on_stdout(w))
        process.readyReadStandardError.connect(lambda w=worker: self._on_stderr(w))
        process.finished.connect(lambda code, status, w=worker: self._on_exit(w))
        process.errorOccurred.connect(lambda error, w=worker: self._on_error(w, error))
        process.start(self._command.program, self._command.arguments)
        process.write(wp.encode_command(self._init))
        self._started += 1
        return worker

    def _dispatch(self, worker):
        if (not worker.ready or worker.partition is not None or self._stopping
                or not self._run_started):         # self-test worker: keep it for run()
            return
        if not self._queue:
            worker.process.write(wp.encode_command(wp.exit_message()))
            return
        worker.partition = self._queue.popleft()
        worker.process.write(wp.encode_command(wp.run_message(worker.partition)))

    def _on_stdout(self, worker):
        worker.buffer += bytes(worker.process.readAllStandardOutput())
        *lines, worker.buffer = worker.buffer.split(b"\n")
        for raw in lines:
            message = wp.parse_line(raw.decode("utf-8", "replace").rstrip("\r"))
            if message:
                self._handle(worker, message)

    def _on_stderr(self, worker):
        text = bytes(worker.process.readAllStandardError()).decode("utf-8", "replace")
        worker.stderr.extend(text.splitlines())

    def _handle(self, worker, message):
        kind = message["type"]
        if kind == "ready":
            worker.ready = True
            if self._ready_waiter is not None:
                self._ready_waiter.quit()
            self._dispatch(worker)
        elif kind == "progress":
            self.progress.emit(message["partition"], message["phase"], message["phase_name"])
        elif kind == "log":
            prefix = f"[{worker.partition}] " if worker.partition else ""
            self.log.emit(message["level"], prefix + message["message"])
        elif kind == "done":
            worker.partition = None
            self.partition_done.emit(message)
            self._dispatch(worker)
            self._check_finished()
        elif kind == "error":
            self.log.emit("WARNING", f"[{message['partition']}] Worker-Fehler: {message['message']} "
                                     "– wird im Hauptprozess nachgerechnet")
            self.recompute.append(message["partition"])
            worker.partition = None
            self._dispatch(worker)
            self._check_finished()

    def _on_error(self, worker, error):
        if error == QProcess.ProcessError.FailedToStart:              # no 'finished' follows
            worker.stderr.append(f"Worker konnte nicht gestartet werden: "
                                 f"{worker.process.errorString()}")
            if self._ready_waiter is not None:
                self._ready_waiter.quit()
            self._on_exit(worker)

    def _alive(self):
        return [w for w in self._workers.values()
                if not w.exited and w.process.state() != QProcess.ProcessState.NotRunning]

    def _on_exit(self, worker):
        if self._stopping or worker.exited:
            return
        worker.exited = True
        if worker.partition is None and not worker.ready:   # died before 'ready'
            self._crashes += 1
            if self._run_started:
                self.log.emit("WARNING", "Worker beendet sich beim Start unerwartet")
        if self._crashes * 2 > self._started and self._queue:    # majority crashed
            self.recompute.extend(self._queue)
            self._queue.clear()
        if worker.partition is not None:                 # crashed during a partition
            self._crashes += 1
            self.recompute.append(worker.partition)
            self.log.emit("WARNING", f"[{worker.partition}] Worker beendet sich unerwartet – "
                                     "wird im Hauptprozess nachgerechnet")
            worker.partition = None
            if self._crashes * 2 > self._started:        # majority crashed -> stop the pool
                self.recompute.extend(self._queue)
                self._queue.clear()
            elif self._queue:
                self._start_worker()
        if self._run_started and self._queue and not self._alive():
            self.log.emit("WARNING", "Kein Worker mehr aktiv – restliche Partitionen werden "
                                     "im Hauptprozess berechnet")
            self.recompute.extend(self._queue)
            self._queue.clear()
        self._check_finished()

    def _check_finished(self):
        busy = any(w.partition is not None for w in self._workers.values())
        if not self._queue and not busy and not self._stopping:
            self._stopping = True
            QTimer.singleShot(0, self._finish)

    def _finish(self):
        for worker in self._workers.values():
            if worker.process.state() != QProcess.ProcessState.NotRunning:
                worker.process.write(wp.encode_command(wp.exit_message()))
                worker.process.waitForFinished(KILL_GRACE_MS)
        self._kill_all()
        self.finished.emit()

    def _kill_all(self):
        for worker in self._workers.values():
            if worker.process.state() != QProcess.ProcessState.NotRunning:
                worker.process.terminate()
                if not worker.process.waitForFinished(KILL_GRACE_MS):
                    worker.process.kill()
                    worker.process.waitForFinished(KILL_GRACE_MS)
