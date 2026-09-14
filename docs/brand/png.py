"""A minimal RGBA PNG writer.

Dithered pixel art alternates colour every pixel, so run-length SVG cannot
merge anything: a 104x116 scene became 5,468 <rect> nodes and the preview
stopped answering. One image node is the right shape for this.
"""
import struct
import zlib


def _rgba(value):
    if value is None:
        return (0, 0, 0, 0)
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255)


def write(path, grid, scale=1):
    """Nearest-neighbour upscale on write: GitHub will not render a pixelated
    image-rendering hint, so the file itself has to carry the final size."""
    w, h = grid.w * scale, grid.h * scale
    raw = bytearray()
    for row in grid.cells:
        line = bytearray()
        for cell in row:
            line.extend(_rgba(cell) * scale)
        for _ in range(scale):
            raw.append(0)
            raw.extend(line)

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    out += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    out += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(out)
    return len(out)
