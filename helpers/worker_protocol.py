# -*- coding: utf-8 -*-
"""JSON-lines protocol between the plugin and its worker processes.

One JSON object per line. Worker → plugin lines start with ``PREFIX`` so that
stray output of QGIS/GDAL on stdout can never be mistaken for a message.
Plugin → worker commands are plain JSON lines on stdin.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import json
from typing import Optional

PREFIX = "IBTOOL "


def encode(message: dict) -> str:
    """Worker → plugin: one prefixed line (JSON escapes newlines inside strings)."""
    return PREFIX + json.dumps(message, ensure_ascii=False) + "\n"


def encode_command(message: dict) -> bytes:
    """Plugin → worker: one UTF-8 JSON line for the worker's stdin."""
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def parse_line(line: str) -> Optional[dict]:
    """Return the message of a prefixed line, ``None`` for anything else."""
    if not line.startswith(PREFIX):
        return None
    try:
        message = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(message, dict) or "type" not in message:
        return None
    return message


def init_message(**fields) -> dict:
    """Plugin → worker, once: inputs, CRS, parameters, workspace, ... (see the worker)."""
    return {"type": "init", **fields}


def run_message(partition: str) -> dict:
    """Plugin → worker: compute one partition."""
    return {"type": "run", "partition": partition}


def exit_message() -> dict:
    """Plugin → worker: finish cleanly."""
    return {"type": "exit"}


def ready_event() -> dict:
    """Worker → plugin: QGIS/Processing initialised (also the self-test)."""
    return {"type": "ready"}


def progress_event(partition: str, phase: int, phase_name: str) -> dict:
    """Worker → plugin: a partition entered *phase* (2–8)."""
    return {"type": "progress", "partition": partition, "phase": phase, "phase_name": phase_name}


def log_event(level: str, message: str) -> dict:
    """Worker → plugin: a log line (the plugin writes it to its log)."""
    return {"type": "log", "level": level, "message": message}


def done_event(partition: str, buildings: int, result_path: Optional[str],
               feature_count: int, seconds: float) -> dict:
    """Worker → plugin: partition finished (``result_path`` None = skipped)."""
    return {"type": "done", "partition": partition, "buildings": buildings,
            "result": result_path, "features": feature_count, "seconds": seconds}


def error_event(partition: str, message: str, traceback_text: str) -> dict:
    """Worker → plugin: partition failed with a Python exception."""
    return {"type": "error", "partition": partition, "message": message,
            "traceback": traceback_text}
