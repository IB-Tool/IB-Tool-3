"""Fake IB-Tool worker for pool tests (no QGIS). Partition name controls behaviour:
'crash*' -> exit(9) mid-partition, 'error*' -> error event, 'slow*' -> sleep 2 s,
anything else -> done. Env FAKE_NO_READY=1 -> never sends ready."""
import json
import os
import sys
import time

PREFIX = "IBTOOL "


def emit(msg):
    sys.stdout.write(PREFIX + json.dumps(msg) + "\n")
    sys.stdout.flush()


init = json.loads(sys.stdin.readline())
print("QGIS noise line that must be ignored", flush=True)
if os.environ.get("FAKE_NO_READY"):
    time.sleep(30)
    sys.exit(0)
emit({"type": "ready"})
for raw in sys.stdin:
    cmd = json.loads(raw)
    if cmd["type"] == "exit":
        break
    name = cmd["partition"]
    emit({"type": "progress", "partition": name, "phase": 2, "phase_name": "Calculate Blocks"})
    if name.startswith("crash"):
        sys.exit(9)
    if name.startswith("error"):
        emit({"type": "error", "partition": name, "message": "boom", "traceback": "tb"})
        continue
    if name.startswith("slow"):
        time.sleep(2)
    emit({"type": "log", "level": "INFO", "message": f"did {name}"})
    emit({"type": "done", "partition": name, "buildings": 10, "result": f"parts/{name}.gpkg",
          "features": 1, "seconds": 0.0})
