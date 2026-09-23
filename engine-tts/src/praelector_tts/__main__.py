# SPDX-License-Identifier: Apache-2.0
"""Worker entry point. Spawned by the engine, one per TTS parallel slot."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from praelector_tts import __version__
from praelector_tts.backends import UnknownBackendError, available_backend_ids, create_backend
from praelector_tts.worker import Worker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praelector-tts-worker",
        description="JSONL stdio TTS worker. Spawned by the engine, not run by hand.",
    )
    parser.add_argument("--version", action="version", version=f"praelector-tts {__version__}")
    parser.add_argument(
        "--backend",
        default="fake",
        help=f"backend id (available: {', '.join(available_backend_ids())})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="stderr log level; stdout is reserved for the protocol",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # stderr only: a log line on stdout would be parsed as a protocol response.
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(str(args.log_level).upper(), logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )

    try:
        backend = create_backend(args.backend)
    except UnknownBackendError as exc:
        print(
            f"praelector-tts-worker: unknown backend {exc.backend_id!r}; "
            f"known: {', '.join(exc.known)}",
            file=sys.stderr,
        )
        return 2

    return Worker(backend, stdin=sys.stdin, stdout=sys.stdout).serve()


if __name__ == "__main__":
    raise SystemExit(main())
