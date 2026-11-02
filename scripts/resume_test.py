"""Resume test: kill a worker-mode run mid-way, resume it, compare with the reference.

1. starts ``profile_pipeline.py --workers N --out <out>`` and kills it hard
   (like a crash / power loss) once ``--kill-after`` partitions are in the
   finish log,
2. reruns it with ``--resume`` and checks that the finished partitions were
   skipped,
3. compares the result with the reference (``compare_results.py``) — must be
   IDENTICAL.

Run with the QGIS Python (Windows example):

    "C:\\Program Files\\QGIS 3.40.0\\bin\\python-qgis.bat" scripts\\resume_test.py ^
        --out %TEMP%\\ibtool_resume --reference <reference.gpkg>

Not part of the plugin package (development tool only). Exit code 0 = passed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--out", required=True, help="Working folder (deleted at start)")
ap.add_argument("--reference", required=True, help="Reference result for compare_results.py")
ap.add_argument("--workers", type=int, default=3)
ap.add_argument("--kill-after", type=int, default=25,
                help="Kill the first run when this many partitions are finished")
ap.add_argument("--timeout", type=int, default=1800, help="Seconds per run")
args = ap.parse_args()

OUT = Path(args.out)
LOG_FIN = OUT / "IB_Tool_Results" / "IB_Tool2_Log_Fin.txt"
PIPELINE = [sys.executable, str(PLUGIN / "scripts" / "profile_pipeline.py"),
            "--out", str(OUT), "--no-cprofile", "--workers", str(args.workers)]


def finished_count():
    """Complete lines in the finish log (a partial last line does not count)."""
    try:
        text = LOG_FIN.read_text(encoding="utf-8")
    except OSError:
        return 0
    return sum(1 for line in text.split("\n")[:-1] if line.strip())


def worker_pids():
    """PIDs of running IB-Tool worker processes (Windows, via CIM)."""
    # Only python processes: the PowerShell query's own command line contains the pattern
    query = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
             "$_.CommandLine -like '*partition_worker.py*' } | ForEach-Object { $_.ProcessId }")
    # The QGIS environment's PATH does not contain the Windows PowerShell folder
    powershell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                              "WindowsPowerShell", "v1.0", "powershell.exe")
    out = subprocess.run([powershell, "-NoProfile", "-Command", query],
                         capture_output=True, text=True, check=False).stdout
    return [int(pid) for pid in out.split() if pid.isdigit()]


def main():
    if worker_pids():
        print("FAIL: worker processes are already running (another IB-Tool run?)")
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)

    # 1. first run, killed hard
    first = subprocess.Popen(PIPELINE, cwd=PLUGIN, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + args.timeout
    while finished_count() < args.kill_after:
        if first.poll() is not None:
            print(f"FAIL: first run ended before {args.kill_after} partitions were finished")
            return 1
        if time.monotonic() > deadline:
            first.kill()
            print("FAIL: timeout in the first run")
            return 1
        time.sleep(0.2)
    first.kill()
    first.wait()
    killed_at = finished_count()
    print(f"first run killed with {killed_at} partitions in the finish log")

    # Orphaned workers must notice the missing parent (stdin EOF / parent check)
    waited = time.monotonic()
    while worker_pids() and time.monotonic() - waited < 60:
        time.sleep(1)
    left = worker_pids()
    if left:
        print(f"FAIL: orphaned worker processes still running after 60 s: {left}")
        return 1
    print(f"orphaned workers gone after {time.monotonic() - waited:.1f} s")

    # 2. resume
    second = subprocess.run(PIPELINE + ["--resume"], cwd=PLUGIN, capture_output=True,
                            text=True, timeout=args.timeout, check=False)
    match = re.search(r"to do: (\d+) of (\d+) partitions", second.stdout)
    if second.returncode != 0 or not match:
        print("FAIL: resume run failed\n" + second.stdout[-3000:] + second.stderr[-3000:])
        return 1
    todo, total = int(match.group(1)), int(match.group(2))
    print(f"resume run: {todo} of {total} partitions to do")
    if total - todo < killed_at:
        print(f"FAIL: resume skipped only {total - todo} partitions, "
              f"{killed_at} were finished")
        return 1

    # 3. compare with the reference
    compare = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "compare_results.py"), args.reference,
         str(OUT / "result.gpkg"), "--parts", str(PLUGIN / "Testdaten" / "A_PART.shp")],
        cwd=PLUGIN, capture_output=True, text=True, check=False)
    verdict = [line for line in compare.stdout.splitlines() if line.startswith("RESULT")]
    print(verdict[-1] if verdict else compare.stdout[-2000:])
    return 0 if verdict and verdict[-1] == "RESULT: IDENTICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
