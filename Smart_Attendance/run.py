"""
Self-restarting supervisor for the SmartAttendance server.
Automatically recovers from WinError 64 (Windows network IOCP crash).
"""
import subprocess
import sys
import time
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

UVICORN_CMD = [
    sys.executable, "-m", "uvicorn", "app.main:app",
    "--host", "0.0.0.0", "--port", "8000",
]

while True:
    print("[supervisor] Starting server...", flush=True)
    result = subprocess.run(UVICORN_CMD)

    if result.returncode == 0:
        print("[supervisor] Server stopped cleanly.")
        break

    print(f"[supervisor] Server crashed (code {result.returncode}). "
          f"Restarting in 3 seconds...", flush=True)
    time.sleep(3)
