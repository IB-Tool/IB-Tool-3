# -*- coding: utf-8 -*-
"""Platform-specific part of the worker mode (parallel partitions).

Everything that depends on the operating system lives here: how to start a
worker (interpreter + script), how many workers to use by default and how a
worker checks that the QGIS process still exists. Worker mode is currently
implemented for Windows (OSGeo4W and the standalone installer); on other
platforms ``find_worker_command`` returns ``None`` and the plugin runs
sequentially. Supporting a new platform = a new branch in
``find_worker_command`` (and ``parent_alive`` if needed).

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import ctypes
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

WORKER_SCRIPT = os.path.join("ibtool", "partition_worker.py")
"""Worker program, relative to the plugin root."""

MAX_DEFAULT_WORKERS = 4
"""Upper bound of the automatic worker count (more brought no gain on the sample data)."""


@dataclass(frozen=True)
class WorkerCommand:
    """Program and arguments to start one worker process."""
    program: str
    arguments: list = field(default_factory=list)


def find_worker_command(plugin_root: str) -> Optional[WorkerCommand]:
    """Return how to start a worker on this system, or ``None`` (→ sequential).

    Windows: the Python interpreter of the running QGIS (``sys.exec_prefix``);
    ``pythonw.exe`` is preferred so no console window appears. The worker
    inherits the environment of the QGIS process (PATH with the QGIS DLLs,
    QT_PLUGIN_PATH, ...); Python and QGIS paths are passed in the ``init``
    message.

    Args:
        plugin_root: Plugin folder containing ``ibtool/partition_worker.py``.

    Returns:
        The command, or ``None`` if worker mode is not available here.
    """
    if sys.platform != "win32":
        return None
    script = os.path.join(plugin_root, WORKER_SCRIPT)
    if not os.path.isfile(script):
        return None
    for name in ("pythonw.exe", "python.exe"):
        candidate = os.path.join(sys.exec_prefix, name)
        if os.path.isfile(candidate):
            return WorkerCommand(candidate, ["-u", script])
    return None


def physical_core_count() -> int:
    """Number of physical CPU cores (Windows API), else logical cores // 2; at least 1."""
    if sys.platform == "win32":
        try:
            return _windows_physical_cores()
        except (OSError, AttributeError, ValueError):
            pass
    return max(1, (os.cpu_count() or 2) // 2)


def _windows_physical_cores() -> int:
    """Count ``RelationProcessorCore`` entries of ``GetLogicalProcessorInformation``."""
    class _Info(ctypes.Structure):  # pylint: disable=too-few-public-methods  # C struct SLPI
        _fields_ = [("mask", ctypes.c_size_t), ("relationship", ctypes.c_int),
                    ("_union", ctypes.c_byte * 16)]

    kernel32 = ctypes.windll.kernel32
    size = ctypes.c_ulong(0)
    kernel32.GetLogicalProcessorInformation(None, ctypes.byref(size))
    count = size.value // ctypes.sizeof(_Info)
    if count == 0:
        raise ValueError("no processor information")
    buffer = (_Info * count)()
    if not kernel32.GetLogicalProcessorInformation(buffer, ctypes.byref(size)):
        raise OSError("GetLogicalProcessorInformation failed")
    cores = sum(1 for info in buffer if info.relationship == 0)   # RelationProcessorCore
    if cores < 1:
        raise ValueError("no cores reported")
    return cores


def default_worker_count(physical_cores: Optional[int] = None) -> int:
    """``max(1, min(4, physical_cores - 1))`` — leaves one core for QGIS/Windows."""
    cores = physical_cores if physical_cores is not None else physical_core_count()
    return max(1, min(MAX_DEFAULT_WORKERS, cores - 1))


def parent_alive(pid: int) -> bool:
    """True if a process with *pid* exists (workers use it to detect a crashed QGIS)."""
    if sys.platform == "win32":
        synchronize, wait_timeout = 0x00100000, 0x102
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
