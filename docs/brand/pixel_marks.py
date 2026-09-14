"""Generates the Joust pixel-art artboards as .dc.html files."""
import json, os

# ---------------------------------------------------------------- palettes
DUSK = dict(
    sky0="#120f1d", sky1="#1b1730", sky2="#2a2247", sky3="#3c2f5c",
    haze="#5b3f6b", star="#f4e9d2", star2="#9aa8c4",
    field="#27402f", field2="#33543c", dirt="#5e4330", dirt2="#77563d",
    crimson="#c4364a", crimson2="#8f2436",
    gold="#f2b544", gold2="#b87f22",
    steel="#9aa8c4", steel2="#5a6584",
    parch="#f4e9d2", ink="#0b0a12",
    tincture="#2f4a8c",
)
PARCH = dict(
    sky0="#efe3c8", sky1="#efe3c8", sky2="#e6d7b6", sky3="#ddcaa4",
    haze="#ddcaa4", star="#8a6b46", star2="#c2ab84",
    field="#d8c49c", field2="#cbb488", dirt="#b99b6c", dirt2="#a8884f",
    crimson="#7a4326", crimson2="#5c3019",
    gold="#3a2a18", gold2="#5c4428",
    steel="#8a6b46", steel2="#5c4428",
    parch="#3a2a18", ink="#3a2a18",
    tincture="#3a2a18",
)
ARCADE = dict(
    sky0="#000000", sky1="#000000", sky2="#101038", sky3="#1c1c68",
    haze="#2c2ca0", star="#ffffff", star2="#58d0ff",
    field="#00a844", field2="#3cd85c", dirt="#a84800", dirt2="#e07800",
    crimson="#e40058", crimson2="#a00030",
    gold="#fcd800", gold2="#e07800",
    steel="#bcbcbc", steel2="#7c7c7c",
    parch="#ffffff", ink="#000000",
    tincture="#0058f8",
)

# ---------------------------------------------------------- pixel wordmark
# Letters on an 11 x 14 grid, drawn as filled rects (x, y, w, h).
LETTERS = {
    "J": [(7, 0, 3, 12), (0, 11, 10, 3), (0, 8, 3, 6)],
    "O": [(0, 0, 3, 14), (8, 0, 3, 14), (0, 0, 11, 3), (0, 11, 11, 3)],
    "U": [(0, 0, 3, 14), (8, 0, 3, 14), (0, 11, 11, 3)],
    "S": [(0, 0, 11, 3), (0, 0, 3, 8), (0, 5, 11, 3), (8, 5, 3, 9), (0, 11, 11, 3)],
    "T": [(0, 0, 11, 3), (4, 0, 3, 14)],
}
ADVANCE = 15
WORD_W = ADVANCE * 5 - (ADVANCE - 11)


def word(x, y, fill, shadow=None):
    out = []
    for dx, dy, colour in ([(1, 1, shadow)] if shadow else []) + [(0, 0, fill)]:
        for i, ch in enumerate("JOUST"):
            for rx, ry, rw, rh in LETTERS[ch]:
                out.append((x + i * ADVANCE + rx + dx, y + ry + dy, rw, rh, colour))
    return out


# ------------------------------------------------------------------ shield
# Row spans of a heater shield, 32 wide and 38 tall.
SHIELD_ROWS = (
    [(y, 0, 32) for y in range(0, 21)]
    + [(21, 1, 30), (22, 1, 30), (23, 2, 28), (24, 2, 28), (25, 3, 26), (26, 4, 24),
       (27, 5, 22), (28, 6, 20), (29, 7, 18), (30, 8, 16), (31, 9, 14), (32, 10, 12),
       (33, 11, 10), (34, 12, 8), (35, 13, 6), (36, 14, 4), (37, 15, 2)]
)


def shield(x, y, p, border=None, left=None, right=None, counterchange=False):
    """Per-pale shield: a lance on the division line is the device."""
    border = border or p["gold"]
    left = left or p["crimson"]
    right = right or p["tincture"]
    out = [(x + rx, y + ry, rw, 1, border) for ry, rx, rw in SHIELD_ROWS]
    for ry, rx, rw in SHIELD_ROWS:
        if not 2 <= ry <= 35:
            continue
        ix, iw = rx + 2, rw - 4
        if iw <= 0:
            continue
        mid = 16
        if ix < mid:
            out.append((x + ix, y + ry, min(iw, mid - ix), 1, left))
        if ix + iw > mid:
            start = max(ix, mid)
            out.append((x + start, y + ry, ix + iw - start, 1, right))
    # The lance: head, collar, shaft, grip.
    lance = [(15, 4, 2, 1), (15, 5, 2, 1), (14, 6, 4, 1), (14, 7, 4, 1), (13, 8, 6, 1),
             (15, 10, 2, 19)]
    trim = [(13, 9, 6, 1), (14, 20, 4, 2)]
    for rects, shade in ((lance, p["gold"]), (trim, p["gold2"])):
        for rx, ry, rw, rh in rects:
            if not counterchange:
                out.append((x + rx, y + ry, rw, rh, shade))
                continue
            mid = 16
            if rx < mid:
                out.append((x + rx, y + ry, min(rw, mid - rx), rh, right))
            if rx + rw > mid:
                start = max(rx, mid)
                out.append((x + start, y + ry, rx + rw - start, rh, left))
    return out


# ---------------------------------------------------------------- fixtures
def pennant(x, y, h, p, flag=None):
    flag = flag or p["crimson"]
    out = [(x, y, 2, h, p["steel2"]), (x - 1, y + h - 1, 4, 1, p["steel2"]),
           (x, y - 1, 2, 1, p["gold"])]
    for i in range(9):
        out.append((x + 2, y + 1 + i, 11 - i, 1, flag))
    out.append((x + 2, y + 1, 11, 1, p["gold"]))
    return out


def barrier(x, y, w, p):
    out = [(x, y, w, 2, p["dirt2"]), (x, y + 4, w, 2, p["dirt2"])]
    for px in range(x + 2, x + w, 13):
        out.append((px, y - 1, 2, 9, p["dirt"]))
    return out


STARS = [(9, 4), (21, 9), (34, 3), (48, 12), (57, 6), (71, 2), (83, 10), (96, 5),
         (108, 13), (119, 3), (131, 8), (143, 5), (151, 12), (28, 15), (65, 16),
         (114, 17), (17, 11), (88, 15)]


def sky(w, h, p, horizon, starry=True):
    bands = [(0, p["sky0"]), (int(h * 0.20), p["sky1"]), (int(h * 0.36), p["sky2"]),
             (int(h * 0.50), p["sky3"]), (horizon - 3, p["haze"])]
    out = []
    for i, (top, colour) in enumerate(bands):
        bottom = bands[i + 1][0] if i + 1 < len(bands) else horizon
        if bottom > top:
            out.append((0, top, w, bottom - top, colour))
    if starry:
        for sx, sy in STARS:
            if sx < w:
                out.append((sx, sy, 1, 1, p["star"] if (sx + sy) % 3 else p["star2"]))
    out += [(0, horizon, w, 2, p["field2"]), (0, horizon + 2, w, h - horizon - 2, p["field"])]
    return out


# ------------------------------------------------------------------- icons
ICONS = {
    "shield": lambda p: (
        [(1, y, 14, 1, p["gold"]) for y in range(0, 8)]
        + [(2, 8, 12, 1, p["gold"]), (3, 9, 10, 1, p["gold"]), (4, 10, 8, 1, p["gold"]),
           (5, 11, 6, 1, p["gold"]), (6, 12, 4, 1, p["gold"]), (7, 13, 2, 1, p["gold"])]
        + [(3, y, 5, 1, p["crimson"]) for y in range(2, 8)]
        + [(8, y, 5, 1, p["sky1"]) for y in range(2, 8)]
        + [(4, 8, 4, 1, p["crimson"]), (8, 8, 4, 1, p["sky1"]),
           (5, 9, 3, 1, p["crimson"]), (8, 9, 3, 1, p["sky1"]),
           (6, 10, 2, 1, p["crimson"]), (8, 10, 2, 1, p["sky1"]),
           (7, 11, 1, 1, p["crimson"]), (8, 11, 1, 1, p["sky1"])]
    ),
    "lance": lambda p: [
        (7, 0, 2, 2, p["parch"]), (6, 2, 4, 2, p["steel"]), (5, 4, 6, 1, p["steel"]),
        (5, 5, 6, 1, p["gold2"]), (7, 6, 2, 8, p["gold"]), (6, 11, 4, 2, p["crimson"]),
    ],
    "pennant": lambda p: [
        (3, 0, 2, 16, p["steel2"]),
        (5, 1, 9, 1, p["gold"]), (5, 2, 9, 1, p["crimson"]), (5, 3, 8, 1, p["crimson"]),
        (5, 4, 7, 1, p["crimson"]), (5, 5, 6, 1, p["crimson"]), (5, 6, 5, 1, p["crimson2"]),
        (5, 7, 4, 1, p["crimson2"]), (5, 8, 3, 1, p["crimson2"]),
    ],
    "helm": lambda p: [
        (7, 0, 2, 3, p["crimson"]), (6, 1, 4, 1, p["crimson2"]),
        (5, 3, 6, 1, p["steel"]), (4, 4, 8, 3, p["steel"]),
        (4, 7, 8, 2, p["ink"]),
        (4, 9, 8, 3, p["steel"]), (5, 12, 6, 1, p["steel2"]), (6, 13, 4, 1, p["steel2"]),
    ],
    "barrier": lambda p: [
        (1, 4, 14, 2, p["dirt2"]), (1, 9, 14, 2, p["dirt2"]),
        (2, 2, 2, 12, p["dirt"]), (12, 2, 2, 12, p["dirt"]),
    ],
    "cup": lambda p: [
        (4, 2, 8, 5, p["gold"]), (5, 7, 6, 1, p["gold2"]),
        (2, 3, 2, 3, p["gold2"]), (12, 3, 2, 3, p["gold2"]),
        (7, 8, 2, 3, p["gold2"]), (4, 11, 8, 2, p["gold"]), (3, 13, 10, 1, p["gold2"]),
    ],
}


# ------------------------------------------------------------------ output
def svg(rects, w, h):
    body = "".join(
        f'<rect x="{x}" y="{y}" width="{rw}" height="{rh}" fill="{c}"/>'
        for x, y, rw, rh, c in rects
    )
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="100%" '
            f'preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges" '
            f'style="display:block">{body}</svg>')


FONT = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Silkscreen:wght@400;700&amp;display=swap">')


def artboard(path, w, h, inner, extra_css=""):
    doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  {FONT}
  <style>
    body {{ margin: 0; background: transparent; }}
    .pixel {{ image-rendering: pixelated; }}
    .type {{ font-family: 'Silkscreen', 'Courier New', monospace; }}
    a {{ color: #f2b544; }} a:hover {{ color: #c4364a; }}
    {extra_css}
  </style>
</helmet>
{inner}
</x-dc>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
