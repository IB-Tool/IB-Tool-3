# -*- coding: utf-8 -*-
"""IB-Tool worker process: computes partitions for the plugin (worker mode).

Started by ``helpers/worker_pool.py`` with the QGIS Python interpreter.
Protocol: ``helpers/worker_protocol.py``. Reads the ``init`` line first using
only the standard library (sys.path / QGIS paths come from the plugin), then
initialises QGIS once and processes ``run`` commands until ``exit``/EOF.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
import json
import os
import sys
import time
import traceback
import types


def _emit(message):
    """Write one protocol event to stdout (the plugin reads it line by line)."""
    from ibtool.helpers import worker_protocol as wp  # pylint: disable=import-outside-toplevel
    sys.stdout.write(wp.encode(message))
    sys.stdout.flush()


def _bootstrap(init):
    """Set up sys.path and the virtual ``ibtool`` package, then start QGIS + Processing."""
    sys.path[:0] = [p for p in init["sys_path"] if p not in sys.path]
    plugins_dir = os.path.join(init["prefix_path"], "python", "plugins")
    if plugins_dir not in sys.path:                 # 'processing' lives here
        sys.path.append(plugins_dir)
    if "ibtool" not in sys.modules:                 # same virtual package as __init__.py
        pkg = types.ModuleType("ibtool")
        pkg.__path__ = [init["plugin_root"]]
        sys.modules["ibtool"] = pkg
    # pylint: disable=import-outside-toplevel
    from qgis.core import QgsApplication
    QgsApplication.setPrefixPath(init["prefix_path"], True)
    app = QgsApplication([], False)
    app.initQgis()
    from processing.core.Processing import Processing
    Processing.initialize()
    return app


def _open_inputs(init):
    """Open the input GeoPackages; raise if one is not valid."""
    from qgis.core import QgsVectorLayer  # pylint: disable=import-outside-toplevel
    keys = {"layer_hu": "hu", "layer_rn": "rn", "layer_part": "part",
            "aux_layers_line": "aux_line"}
    layers = {}
    for name, key in keys.items():
        layer = QgsVectorLayer(init["inputs"][key], name, "ogr")
        if not layer.isValid():
            raise OSError(f"Eingabe nicht lesbar: {init['inputs'][key]}")
        layers[name] = layer
    return layers


def main():  # pylint: disable=too-many-locals
    """Worker main loop; returns the process exit code."""
    # Pipes default to the ANSI code page on Windows; the protocol is UTF-8.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    line = sys.stdin.readline()
    if not line.strip():
        return 1
    init = json.loads(line)
    # keep the QgsApplication referenced for the whole worker life
    app = _bootstrap(init)  # noqa: F841  pylint: disable=unused-variable

    # pylint: disable=import-outside-toplevel
    from qgis.core import QgsCoordinateReferenceSystem
    from ibtool.helpers import worker_protocol as wp
    from ibtool.helpers.logger import Logger
    from ibtool.helpers.partition_pipeline import run_partition
    from ibtool.helpers.partition_results import write_part_result
    from ibtool.helpers.processing_context import shared_processing_context, ui_heartbeat
    from ibtool.helpers.worker_launcher import parent_alive

    Logger.set_sink(lambda level, message: _emit(wp.log_event(level, message)))  # before any log
    Logger.set_log_level(init["log_level"])

    crs = QgsCoordinateReferenceSystem(init["crs"])
    layers = _open_inputs(init)
    parent_pid = init["parent_pid"]
    last_check = [0.0]

    def _guard():                                   # heartbeat: exit if QGIS is gone
        now = time.monotonic()
        if now - last_check[0] >= 2.0:
            last_check[0] = now
            if not parent_alive(parent_pid):
                os._exit(3)                         # pylint: disable=protected-access

    _emit(wp.ready_event())
    with ui_heartbeat(_guard):
        for raw in sys.stdin:
            if not raw.strip():
                continue
            command = json.loads(raw)
            if command["type"] == "exit":
                break
            name = command["partition"]
            started = time.perf_counter()
            try:
                with shared_processing_context():
                    result, count = run_partition(
                        name, layers, crs, init["workspace"], init["debug_mode"],
                        init["global_density"], init["params"],
                        progress=lambda p, n, _name=name: _emit(wp.progress_event(_name, p, n)))
                    rel, features = (None, 0) if result is None else \
                        write_part_result(result, name, init["results_dir"])
                _emit(wp.done_event(name, count, rel, features, time.perf_counter() - started))
            except Exception as e:  # pylint: disable=broad-exception-caught
                _emit(wp.error_event(name, str(e), traceback.format_exc()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
