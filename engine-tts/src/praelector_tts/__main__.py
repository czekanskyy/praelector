# SPDX-License-Identifier: Apache-2.0
"""JSONL stdio worker event loop."""

from __future__ import annotations

import json
import sys

from praelector_tts.worker import TtsWorker


def main() -> int:
    worker = TtsWorker()

    # Initial ready notification on worker spawn
    sys.stdout.write(
        json.dumps({"event": "ready", "backends": list(worker.backends.keys())}) + "\n"
    )
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            raw_req = json.loads(line)
            resp = worker.handle_request(raw_req)
            sys.stdout.write(resp.model_dump_json() + "\n")
            sys.stdout.flush()

            if raw_req.get("action") == "shutdown":
                break
        except Exception as e:  # noqa: BLE001
            err_resp = {"id": "unknown", "ok": False, "error": str(e)}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
