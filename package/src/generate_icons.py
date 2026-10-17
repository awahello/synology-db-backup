# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
import os
import struct
import sys
import zlib


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def make_png(size):
    pixels = bytearray()
    cx = size / 2.0
    rx = size * 0.30
    ry = size * 0.10
    top = size * 0.25
    bottom = size * 0.72
    bg = (18, 60, 90, 255)
    fg = (239, 248, 255, 255)
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            color = bg
            if top - ry <= y <= bottom + ry:
                if top - ry <= y <= top + ry:
                    inside = ((x - cx) / rx) ** 2 + ((y - top) / ry) ** 2 <= 1
                    if inside and abs(((x - cx) / rx) ** 2 + ((y - top) / ry) ** 2 - 1) < 0.16:
                        color = fg
                elif top + ry < y < bottom:
                    dx = rx * (1.0 if y <= top + 2 * ry else 1.0)
                    if abs(abs(x - cx) - dx) <= max(1, size / 64):
                        color = fg
                    for center in (size * 0.43, size * 0.60):
                        if abs(y - center) <= max(1, size / 64) and abs(x - cx) <= rx:
                            color = fg
                elif bottom - ry <= y <= bottom + ry:
                    eq = ((x - cx) / rx) ** 2 + ((y - bottom) / ry) ** 2
                    if abs(eq - 1) < 0.16 and eq <= 1.2:
                        color = fg
            row.extend(color)
        pixels.extend(row)
    raw = b"\x89PNG\r\n\x1a\n"
    raw += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(bytes(pixels), 9))
    raw += chunk(b"IEND", b"")
    return raw


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for size in (16, 24, 32, 48, 64, 72, 256):
        path = os.path.join(out, "icon_{}.png".format(size))
        with open(path, "wb") as f:
            f.write(make_png(size))
    for size, name in ((64, "PACKAGE_ICON.PNG"), (256, "PACKAGE_ICON_256.PNG")):
        with open(os.path.join(out, name), "wb") as f:
            f.write(make_png(size))


if __name__ == "__main__":
    main()

