#!/usr/bin/env python3
"""
Smoke test for the full pipeline using MOCK_MODE.

Starts the server, connects over WebSocket, drives two messages through
the qualifier + interview handshake, and verifies that every expected
stage is reached without making real API calls.

Usage (two terminals):
  Terminal 1:  MOCK_MODE=1 uvicorn app:app --reload
  Terminal 2:  python tests/mock_pipeline.py

Or run the server inline (requires Python 3.11+):
  MOCK_MODE=1 python tests/mock_pipeline.py --serve
"""
import argparse
import asyncio
import json
import subprocess
import sys
import time
import uuid

try:
    import websockets
except ImportError:
    sys.exit("Install websockets: pip install websockets")

SERVER = "ws://localhost:8000"
EXPECTED_STAGES = {"interview", "analyze", "redteam", "draft", "closure"}


async def run_smoke_test() -> bool:
    session_id = str(uuid.uuid4())
    url = f"{SERVER}/ws/{session_id}"
    stages_seen: list[str] = []
    complete = False

    print(f"Connecting → {url}")
    try:
        async with websockets.connect(url, open_timeout=5) as ws:
            # 1. Set language — server replies with greeting
            await ws.send(json.dumps({"type": "set_language", "language": "en"}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"  ← {msg['type']}: {str(msg.get('text', ''))[:80]}")

            # 2. Trigger qualifier
            await ws.send(json.dumps({
                "type": "message",
                "text": "We run a road freight company with 80 employees in Poland.",
                "language": "en",
            }))

            answers_sent = 0
            max_answers = 12  # interviewer requires ≥ 8 questions before completing

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    print("  TIMEOUT waiting for next message")
                    break

                msg = json.loads(raw)
                mtype = msg.get("type", "")
                label = msg.get("text") or msg.get("stage") or msg.get("data", "")
                print(f"  ← {mtype}: {str(label)[:100]}")

                if mtype == "stage_change":
                    stages_seen.append(msg.get("stage", ""))

                # Keep answering interview questions until the mock advances
                # to analysis. The mock interviewer requires at least 8 exchanges.
                if (
                    mtype == "agent_message"
                    and msg.get("stage") == "interview"
                    and answers_sent < max_answers
                ):
                    answers_sent += 1
                    await asyncio.sleep(0.2)
                    await ws.send(json.dumps({
                        "type": "message",
                        "text": f"Mock interview answer {answers_sent} — basic passwords, Gmail, no training.",
                        "language": "en",
                    }))

                if mtype == "complete":
                    complete = True
                    data = msg.get("data", {}) or {}
                    plans = (data.get("closure_plans") or {}).get("closure_plans") or []
                    print(f"  closure_plans in payload: {len(plans)}")
                    break

    except OSError as exc:
        print(f"Could not connect to {SERVER} — is the server running? ({exc})")
        return False

    print()
    print(f"Stages seen : {stages_seen}")
    missing = EXPECTED_STAGES - set(stages_seen)
    if missing:
        print(f"FAIL — missing stages: {missing}")
        return False
    if not complete:
        print("FAIL — 'complete' event never received")
        return False
    print("PASS — all expected stages reached and pipeline completed")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--serve", action="store_true",
        help="Spin up the uvicorn server in a subprocess before running the test"
    )
    args = parser.parse_args()

    proc = None
    if args.serve:
        import os
        env = {**os.environ, "MOCK_MODE": "1"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"],
            env=env,
        )
        time.sleep(2)  # wait for server startup

    try:
        ok = asyncio.run(run_smoke_test())
    finally:
        if proc:
            proc.terminate()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
