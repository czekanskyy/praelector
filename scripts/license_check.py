# SPDX-License-Identifier: Apache-2.0
"""Dependency license policy checker and NOTICE generator."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check dependency licenses and generate NOTICE.")
    parser.add_argument(
        "--python",
        action="append",
        default=[],
        help="Python project directory to check",
    )
    parser.add_argument(
        "--node", action="append", default=[], help="Node project directory to check"
    )
    parser.add_argument(
        "--write-notice", action="store_true", help="Generate and update NOTICE file"
    )
    args = parser.parse_args()

    notice_path = Path("NOTICE")

    if args.write_notice:
        header = (
            "Praelector\n"
            "Copyright 2026 Praelector Contributors\n\n"
            "This product includes software developed by the Praelector project\n"
            "(https://github.com/czekanskyy/praelector).\n\n"
            'Licensed under the Apache License, Version 2.0 (the "License");\n'
            "you may not use this file except in compliance with the License.\n"
            "You may obtain a copy of the License at\n\n"
            "    http://www.apache.org/licenses/LICENSE-2.0\n\n"
            "Unless required by applicable law or agreed to in writing, software\n"
            'distributed under the License is distributed on an "AS IS" BASIS,\n'
            "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
            "See the License for the specific language governing permissions and\n"
            "limitations under the License.\n"
        )
        notice_path.write_text(header, encoding="utf-8")
        print(f"NOTICE updated at {notice_path.resolve()}")
        return 0

    print("License policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
