"""
Interactive Unknown-Face Enrollment Tool
=========================================
Run this in a second terminal while the server is running.

What it does:
  1. Connects to the server WebSocket and listens for unknown face events
  2. When an unknown face appears on camera, it beeps + prints an alert
  3. You type Y to enroll, N to skip
  4. Enter the person's Name and Employee ID
  5. Script captures 5 snapshots from the live camera
  6. Sends them to POST /enroll — person is immediately live in the system

Usage (from project root):
    venv/Scripts/python.exe scripts/enroll_unknown.py
"""

import asyncio
import io
import sys
import time
import threading
import json

import requests
import websockets

BASE_URL  = "http://localhost:8000"
WS_URL    = "ws://localhost:8000/ws/events"
SNAPSHOTS = 5
SNAP_GAP  = 0.4


def beep():
    try:
        import winsound
        winsound.Beep(880, 300)
    except Exception:
        print("\a", end="", flush=True)


def capture_snapshots(n: int, gap: float) -> list[bytes]:
    frames = []
    for i in range(n):
        try:
            r = requests.get(f"{BASE_URL}/snapshot", timeout=3)
            if r.status_code == 200:
                frames.append(r.content)
                print(f"  [snap {i+1}/{n}] captured")
        except Exception as e:
            print(f"  [snap {i+1}] failed: {e}")
        time.sleep(gap)
    return frames


def do_enroll(name: str, employee_id: str, department: str = "") -> dict:
    print(f"\nCapturing {SNAPSHOTS} frames — stand still!")
    frames = capture_snapshots(SNAPSHOTS, SNAP_GAP)
    if not frames:
        return {"error": "No frames captured — is the camera on?"}

    files = [("images", (f"snap_{i}.jpg", io.BytesIO(f), "image/jpeg"))
             for i, f in enumerate(frames)]
    data = {"name": name, "employee_id": employee_id}
    if department:
        data["department"] = department

    try:
        resp = requests.post(f"{BASE_URL}/enroll", data=data, files=files, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def prompt_enroll():
    print("\n" + "-" * 50)
    print("  ENROLL NEW PERSON")
    print("-" * 50)

    name = input("  Full name       : ").strip()
    if not name:
        print("  Cancelled.")
        return

    employee_id = input("  Employee ID     : ").strip()
    if not employee_id:
        print("  Cancelled.")
        return

    department = input("  Department (opt): ").strip()

    result = do_enroll(name, employee_id, department)

    if "error" in result:
        print(f"\n  FAILED: {result['error']}")
    else:
        print(f"\n  Enrolled '{name}'  |  person_id={result.get('person_id')}"
              f"  |  embeddings={result.get('embeddings_added')}")
        print("  Person is now live — step in front of the camera to verify.\n")


_enroll_flag = threading.Event()

def _input_worker():
    while True:
        try:
            ch = input()
            if ch.strip().upper() in ("E", "ENROLL"):
                _enroll_flag.set()
        except EOFError:
            break


async def listen():
    print("=" * 60)
    print("  SmartAttendance — Unknown-Face Enrollment Tool")
    print("=" * 60)
    print(f"  Connecting to {WS_URL} ...\n")
    print("  Tip: type  E  any time to manually trigger enrollment\n")

    t = threading.Thread(target=_input_worker, daemon=True)
    t.start()

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                print("  Connected. Watching for unknown faces...\n")
                async for raw in ws:
                    evt = json.loads(raw)

                    if evt.get("type") == "unknown_face":
                        beep()
                        print("\n" + "!" * 60)
                        print("!  UNKNOWN FACE DETECTED")
                        print("!" * 60)
                        print("  Enroll this person? [Y/N] : ", end="", flush=True)

                        answer = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: input().strip().upper()
                        )
                        if answer == "Y":
                            await asyncio.get_event_loop().run_in_executor(
                                None, prompt_enroll
                            )
                        else:
                            print("  Skipped.\n")

                    elif evt.get("type") == "checkin":
                        print(f"  CHECK IN  | {evt.get('person_name')}"
                              f" | {evt.get('confidence', 0)*100:.1f}%")

                    elif evt.get("type") == "checkout":
                        print(f"  CHECK OUT | {evt.get('person_name')}"
                              f" | {evt.get('absent_for_min', 0)} min")

                    if _enroll_flag.is_set():
                        _enroll_flag.clear()
                        await asyncio.get_event_loop().run_in_executor(
                            None, prompt_enroll
                        )

        except (websockets.ConnectionClosed, OSError) as e:
            print(f"\n  Connection lost ({e}) — retrying in 3s...")
            await asyncio.sleep(3)
        except KeyboardInterrupt:
            print("\n  Exiting.")
            break


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\nBye.")
