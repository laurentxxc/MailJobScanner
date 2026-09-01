#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"
DASHBOARD = ROOT / "dashboard.py"
PID_FILE = ROOT / ".dashboard.pid"
URL = "http://localhost:8501"


def launch():
    stop()
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "streamlit", "run", str(DASHBOARD)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    PID_FILE.write_text(str(proc.pid))
    for _ in range(30):
        if proc.poll() is not None:
            print("Streamlit exited prematurely.")
            sys.exit(1)
        try:
            urllib.request.urlopen(URL)
            break
        except Exception:
            time.sleep(1)
    webbrowser.open(URL)
    try:
        proc.wait()
    except KeyboardInterrupt:
        stop()


def _is_our_pid(pid):
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return False
    return "streamlit" in out and str(ROOT) in out


def stop():
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        if _is_our_pid(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
            except (ProcessLookupError, PermissionError):
                pass
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    launch()
