# SPDX-License-Identifier: Apache-2.0
"""A JSONL worker for tests. Modes: ok, hang-ready, hang-call."""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
    if mode == "hang-ready":
        time.sleep(30)
    sys.stdout.write(
        json.dumps({"event": "ready", "pid": 0, "device": "cpu", "torch": "fake"}) + "\n"
    )
    sys.stdout.flush()
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("op") == "shutdown":
            return
        if mode == "hang-call":
            time.sleep(30)
        reply = {"id": message["id"], "ok": True, "result": {"echo": message.get("op")}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
