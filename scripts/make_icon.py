"""Draw the NightOwl crescent icon."""

from __future__ import annotations

import struct
from pathlib import Path


def _pixel(size: int, x: int, y: int) -> bytes:
    cx = (x + 0.5) - size / 2
    cy = (y + 0.5) - size / 2
    radius = (cx * cx + cy * cy) ** 0.5
    limit = size * 0.46
    if radius > limit:
        return b"\x00\x00\x00\x00"
    hole_x = cx - size * 0.16
    hole_y = cy - size * 0.08
    hole = (hole_x * hole_x + hole_y * hole_y) ** 0.5
    if radius < size * 0.34 and hole > size * 0.24:
        return bytes((0x4A, 0xA1, 0xF0, 255))
    return bytes((0x0B, 0x0D, 0x0E, 255))


def _image(size: int) -> bytes:
    rows = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            rows += _pixel(size, x, y)
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(rows) + len(mask), 0, 0, 0, 0)
    return header + bytes(rows) + mask


def write_ico(path: Path) -> None:
    images = [_image(size) for size in (16, 32, 48, 256)]
    offset = 6 + 16 * len(images)
    entries = bytearray()
    blob = bytearray()
    for size, image in zip((16, 32, 48, 256), images):
        stored = 0 if size == 256 else size
        entries += struct.pack("<BBBBHHII", stored, stored, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
        blob += image
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + bytes(entries) + bytes(blob))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    write_ico(root / "assets" / "nightowl.ico")
    print(root / "assets" / "nightowl.ico")
