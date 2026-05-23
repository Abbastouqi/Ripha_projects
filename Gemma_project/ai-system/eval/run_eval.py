"""
Eval harness for the local AI platform.

Runs every case in test_cases.json through the running backend (defaults to
http://localhost:8000) and reports:
  - Routing accuracy: did the backend dispatch to the expected workflow?
  - Substring accuracy: when expect_substrings is set, did the answer
    contain any of them?
  - Latency per case (wall-clock)

Outputs a per-case table and a summary. Exit code is 0 if routing accuracy
>= ROUTING_THRESHOLD (default 0.8), else 1 — convenient for CI.

Usage:
    python eval/run_eval.py
    python eval/run_eval.py --backend http://localhost:8000 --cases eval/test_cases.json
    python eval/run_eval.py --use-openai-compat   # uses /v1/chat/completions instead of /api/chat
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

try:
    import httpx
except ImportError:
    print("This script needs httpx. Install with: pip install httpx")
    sys.exit(1)


ROUTING_THRESHOLD = float(os.getenv("EVAL_ROUTING_THRESHOLD", "0.8"))


def call_chat_api(backend: str, query: str) -> dict:
    r = httpx.post(
        f"{backend}/api/chat",
        json={"text": query},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


def call_openai_compat(backend: str, query: str, api_key: str = "") -> dict:
    """Use the OpenAI-compatible /v1/chat/completions endpoint."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    r = httpx.post(
        f"{backend}/v1/chat/completions",
        json={
            "model": "local-ai-auto",
            "messages": [{"role": "user", "content": query}],
        },
        headers=headers,
        timeout=120.0,
    )
    r.raise_for_status()
    j = r.json()
    return {
        "response": j["choices"][0]["message"]["content"],
        "workflow": j.get("x_workflow", "unknown"),
        "sources": j.get("x_sources", []),
    }


def check_case(case: dict, result: dict) -> dict:
    expected_wf = case.get("expected_workflow")
    actual_wf = result.get("workflow", "unknown")
    routing_ok = (actual_wf == expected_wf) if expected_wf else True

    substr_ok = True
    substrs = case.get("expect_substrings") or []
    if substrs:
        answer = (result.get("response") or "").lower()
        substr_ok = any(s.lower() in answer for s in substrs)

    return {"routing_ok": routing_ok, "substr_ok": substr_ok, "actual_workflow": actual_wf}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--cases", default=str(Path(__file__).parent / "test_cases.json"))
    parser.add_argument("--use-openai-compat", action="store_true",
                        help="Hit /v1/chat/completions instead of /api/chat")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_COMPAT_API_KEY", ""))
    args = parser.parse_args()

    with open(args.cases, encoding="utf-8") as f:
        spec = json.load(f)
    cases = spec.get("cases", [])

    print()
    print("=" * 80)
    print(f" Local AI Platform — Eval Harness")
    print(f" Backend:   {args.backend}")
    print(f" Endpoint:  {'/v1/chat/completions' if args.use_openai_compat else '/api/chat'}")
    print(f" Cases:     {len(cases)}")
    print("=" * 80)
    print()

    # Header
    print(f"{'ID':<22} {'Expected WF':<22} {'Actual WF':<22} {'Routing':<8} {'Substr':<7} {'ms':>6}")
    print("-" * 92)

    routing_pass = 0
    substr_pass = 0
    substr_total = 0
    total_ms = 0

    for case in cases:
        cid = case.get("id", "?")
        query = case.get("query", "")
        start = time.time()
        try:
            if args.use_openai_compat:
                result = call_openai_compat(args.backend, query, args.api_key)
            else:
                result = call_chat_api(args.backend, query)
        except Exception as e:
            print(f"{cid:<22} ERROR: {e}")
            continue
        elapsed_ms = int((time.time() - start) * 1000)
        total_ms += elapsed_ms

        check = check_case(case, result)
        if check["routing_ok"]:
            routing_pass += 1
        if case.get("expect_substrings"):
            substr_total += 1
            if check["substr_ok"]:
                substr_pass += 1

        r_mark = "PASS " if check["routing_ok"] else "FAIL "
        s_mark = "PASS " if check["substr_ok"] else "FAIL "
        if not case.get("expect_substrings"):
            s_mark = "  -  "

        print(
            f"{cid:<22} "
            f"{(case.get('expected_workflow') or '-'):<22} "
            f"{check['actual_workflow']:<22} "
            f"{r_mark:<8} {s_mark:<7} {elapsed_ms:>6}"
        )

    print("-" * 92)
    routing_acc = routing_pass / max(1, len(cases))
    substr_acc = (substr_pass / substr_total) if substr_total else 1.0
    print()
    print(f" Routing accuracy:   {routing_pass}/{len(cases)} = {routing_acc:.1%}")
    if substr_total:
        print(f" Substring accuracy: {substr_pass}/{substr_total} = {substr_acc:.1%}")
    print(f" Avg latency:        {total_ms // max(1, len(cases))} ms / case")
    print()

    if routing_acc < ROUTING_THRESHOLD:
        print(f" FAIL: routing accuracy below threshold ({ROUTING_THRESHOLD:.0%}).")
        sys.exit(1)
    print(f" OK: routing accuracy meets threshold ({ROUTING_THRESHOLD:.0%}).")


if __name__ == "__main__":
    main()
