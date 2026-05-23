"""
PC AI Assistant — command-line entry point.

Run from the project root:
    python pc_ai_assistant.py

Examples:
    Command: open admissions portal
    Command: diagnose portal
    Command: login
    Command: register
    Command: apply for admission
    Command: check application status
    Command: help
    Command: quit
"""

import os
import sys

# ── Windows asyncio fix (Playwright needs ProactorEventLoop) ─────────────────
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ── Add project root to path so `backend.*` imports work ─────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
import yaml

from backend.automation.agent.voice import listen_for_command
from backend.automation.agent.command_router import route_command


def load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(cfg_path):
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    load_dotenv()
    config = load_config()

    print("\033[36;1m")
    print("╔══════════════════════════════════════════════╗")
    print("║      Riphah PC AI Assistant  v1.0           ║")
    print("╚══════════════════════════════════════════════╝")
    print("\033[0m")
    print("Type a command, or press Enter to use voice (if enabled in config.yaml).")
    print("Examples:  open admissions portal  |  apply for admission  |  help  |  quit\n")

    while True:
        try:
            text = input("\033[32mCommand\033[0m (or Enter for voice): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        # ── Voice fallback ────────────────────────────────────────────────────
        if not text:
            voice_cfg = config.get("voice", {})
            if voice_cfg.get("enabled", False):
                text = listen_for_command(language=voice_cfg.get("language", "en-US"))
            else:
                print("  (Voice disabled — enable it in config.yaml)")
                continue

        if not text:
            continue

        if text.lower() in ("quit", "exit", "stop", "bye"):
            print("Goodbye.")
            break

        route_command(text, config)


if __name__ == "__main__":
    main()
