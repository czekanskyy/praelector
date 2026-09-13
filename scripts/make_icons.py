# SPDX-License-Identifier: Apache-2.0
"""Generate placeholder application icons for Tauri."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def create_png(width: int, height: int, r: int, g: int, b: int, a: int) -> bytes:
    raw_data = bytearray()
    row = bytearray([0]) + bytearray([r, g, b, a] * width)
    for _ in range(height):
        raw_data.extend(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_data))

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def create_ico(png_data: bytes, width: int, height: int) -> bytes:
    header = struct.pack("<HHH", 0, 1, 1)
    w = 0 if width >= 256 else width
    h = 0 if height >= 256 else height
    entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_data), 6 + 16)
    return header + entry + png_data


def main() -> int:
    icons_dir = Path("apps/desktop/icons")
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Deep blue / indigo Praelector icon color: RGBA(40, 60, 160, 255)
    png_32 = create_png(32, 32, 40, 60, 160, 255)
    png_128 = create_png(128, 128, 40, 60, 160, 255)
    png_256 = create_png(256, 256, 40, 60, 160, 255)

    (icons_dir / "32x32.png").write_bytes(png_32)
    (icons_dir / "128x128.png").write_bytes(png_128)
    (icons_dir / "128x128@2x.png").write_bytes(png_256)
    (icons_dir / "icon.ico").write_bytes(create_ico(png_32, 32, 32))
    (icons_dir / "icon.icns").write_bytes(png_128)  # Placeholder

    print(f"Generated icons in {icons_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
