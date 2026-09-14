"""The three scenes, redrawn: shaded, and each on its own framing and palette."""
import sys
sys.path.insert(0, ".")
from shade import OUTLINE, RAMPS, Shade, pick

SK, GO, SI, WO = RAMPS["skin"], RAMPS["gold"], RAMPS["silk"], RAMPS["wood"]
ST, HA, TO = RAMPS["steel"], RAMPS["hair"], RAMPS["torch"]


def wash(g, ramp, *, top=0.95, bottom=0.34, vignette=0.30):
    colours = RAMPS[ramp]
    for y in range(g.h):
        for x in range(g.w):
            k = top + (bottom - top) * (y / g.h)
            k -= (abs(x - g.w / 2) / (g.w / 2)) ** 2 * vignette
            g.put(x, y, pick(colours, k, x, y))


def edge(g, colour=OUTLINE):
    filled = [[c is not None for c in row] for row in g.cells]
    for y in range(g.h):
        for x in range(g.w):
            if filled[y][x]:
                continue
            if any(0 <= y + dy < g.h and 0 <= x + dx < g.w and filled[y + dy][x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                g.put(x, y, colour)


def over(base, layer):
    for y in range(base.h):
        for x in range(base.w):
            if layer.cells[y][x] is not None:
                base.cells[y][x] = layer.cells[y][x]


# ------------------------------------------------------------------ Favour
FW, FH = 120, 88


def favour():
    """Macro: her hand knotting the silk onto the lance. Dawn, not night."""
    g = Shade(FW, FH)
    wash(g, "dawn", top=0.90, bottom=0.30, vignette=0.26)
    for bx in (18, 92):                                        # soft banners behind
        g.slab([(bx - 7, 0), (bx + 7, 0), (bx + 7, 30), (bx - 7, 30)], "mist",
               t0=0.22, t1=0.48)

    art = Shade(FW, FH)
    art.rod(-6, 84, 126, 18, 7, "wood", bias=0.04)             # the lance
    for fx in (46, 88):                                        # ferrules
        fy = 84 - 66 * ((fx + 6) / 132)
        art.rod(fx - 3, fy + 2, fx + 3, fy - 1, 9, "steel", bias=0.06)

    # The favour: a knot on the shaft, then silk streaming back down the wind.
    # A band passing behind the shaft, then the knot and tails in front of it.
    art.slab([(58, 34), (70, 28), (78, 44), (66, 50)], "silk", t0=0.24, t1=0.62)
    art.rod(-6, 84, 126, 18, 7, "wood", bias=0.04)
    art.slab([(60, 40), (72, 34), (80, 50), (68, 56)], "silk", t0=0.40, t1=0.98)
    art.sphere(69, 45, 9, 7, "silk", bias=0.10)
    for pts in (((64, 48), (73, 52), (49, 68), (40, 63)),
                ((49, 64), (59, 68), (33, 82), (24, 75))):
        art.slab(list(pts), "silk", t0=0.30, t1=0.92, axis="y")
    for x, y in ((63, 40), (70, 38), (58, 52), (48, 62), (38, 72), (30, 78)):
        art.put(x, y, SI[4])

    # Her hand, closing on the shaft: palm, four fingers, a thumb, a cuff.
    art.sphere(99, 30, 14, 12, "skin", bias=0.02)
    for i, (fx, fy) in enumerate(((88, 33), (91, 39), (95, 44), (100, 47))):
        art.rod(fx + 9, fy - 4, fx, fy, 3, "skin", bias=0.04 - i * 0.03)
    art.rod(96, 20, 86, 29, 3, "skin", bias=0.10)
    art.slab([(104, 16), (120, 12), (120, 44), (108, 46)], "blue", t0=0.26, t1=0.74)
    art.slab([(103, 18), (112, 15), (114, 41), (105, 44)], "gold", t0=0.44, t1=0.94)
    edge(art)
    over(g, art)
    return g


# ------------------------------------------------------------------- Prize
PW, PH = 104, 116


def prize():
    """Low angle, torchlit: over the victor's bare head, up at the stand."""
    g = Shade(PW, PH)
    wash(g, "torch", top=0.34, bottom=0.06, vignette=0.22)
    for tx in (9, 95):
        g.glow(tx, 34, 26, "torch", strength=0.85)

    art = Shade(PW, PH)
    # Canopy and its valance.
    art.slab([(0, 2), (PW, 2), (PW, 11), (0, 11)], "wood", t0=0.30, t1=0.78)
    for i, px in enumerate(range(-2, PW + 8, 11)):
        art.slab([(px, 11), (px + 11, 11), (px + 6, 21)], "silk" if i % 2 else "gold",
                 t0=0.34, t1=0.86, axis="y")

    # The royal party behind the rail.
    for cx, robe, crowned in ((30, "blue", True), (62, "silk", True)):
        art.slab([(cx - 13, 40), (cx + 13, 40), (cx + 16, 64), (cx - 16, 64)], robe,
                 t0=0.26, t1=0.74)
        art.sphere(cx, 28, 11, 10, "hair", bias=-0.06)
        art.sphere(cx, 34, 9, 10, "skin", bias=0.02)
        for ex in (-4, 4):                                     # eyes, brow, mouth
            art.put(cx + ex, 33, HA[0]); art.put(cx + ex + 1, 33, HA[0])
            art.put(cx + ex, 31, HA[1])
        art.put(cx, 36, SK[4]); art.put(cx, 37, SK[1])
        art.put(cx - 2, 40, HA[1]); art.put(cx - 1, 40, HA[1]); art.put(cx, 40, HA[1])
        if crowned:
            art.slab([(cx - 11, 17), (cx + 11, 17), (cx + 11, 23), (cx - 11, 23)], "gold",
                     t0=0.46, t1=1.0)
            for k in (-9, -2, 5):
                art.slab([(cx + k, 11), (cx + k + 4, 11), (cx + k + 4, 18), (cx + k, 18)],
                         "gold", t0=0.56, t1=1.0)
    # Her arm comes down over the rail with the chaplet.
    art.rod(70, 56, 50, 80, 4, "skin", bias=0.04)
    art.sphere(47, 83, 5, 5, "skin", bias=0.06)
    art.sphere(44, 91, 12, 11, "gold", bias=0.02)
    art.sphere(44, 91, 6, 6, None) if False else None
    for y in range(85, 98):                                    # open the ring
        for x in range(38, 51):
            if ((x - 44) / 6.0) ** 2 + ((y - 91) / 5.5) ** 2 <= 1.0:
                art.cells[y][x] = None
    # The rail, in front of them.
    art.rod(-4, 68, PW + 4, 68, 5, "wood", bias=0.08)
    for px in range(6, PW, 24):
        art.slab([(px, 64), (px + 5, 64), (px + 5, 74), (px, 74)], "wood", t0=0.18, t1=0.52)

    # Torch staves, and the victor's bare head filling the foreground.
    for tx in (9, 95):
        art.rod(tx, 26, tx, 60, 3, "wood", bias=-0.06)
        art.sphere(tx, 28, 6, 8, "torch", bias=0.20)
        art.slab([(tx - 4, 22), (tx + 4, 22), (tx + 1, 8), (tx - 2, 8)], "torch",
                 t0=0.62, t1=1.0, axis="y")
    art.sphere(52, 112, 25, 21, "hair", bias=-0.30)
    for k in range(-25, 26, 2):                                # rim light on his head
        yy = 112 - int((1 - (k / 26) ** 2) ** 0.5 * 21)
        art.put(52 + k, yy, TO[3] if k < 4 else HA[2])
        art.put(52 + k, yy + 1, HA[1])
    art.slab([(0, 108), (24, 100), (26, PH), (0, PH)], "steel", t0=0.14, t1=0.44)
    art.slab([(80, 100), (PW, 108), (PW, PH), (78, PH)], "steel", t0=0.10, t1=0.38)
    edge(art)
    over(g, art)
    return g


# ---------------------------------------------------------------- Parallax
def rider(stride=0):
    """The walking horse and rider, modelled instead of blacked in."""
    g = Shade(78, 64)
    if stride:
        legs = ((46, 36, 53, 55), (42, 36, 37, 55), (16, 36, 11, 53), (22, 38, 27, 55))
    else:
        legs = ((46, 36, 59, 53), (42, 36, 48, 57), (16, 36, 4, 51), (22, 38, 16, 57))
    for x0, y0, x1, y1 in legs:
        g.rod(x0, y0, x1, y1, 3, "bay", bias=-0.14)
        g.rod(x1, y1, x1, y1 + 4, 3, "hair", bias=-0.10)
    g.rod(8, 28, 2, 44, 3, "hair", bias=-0.08)                 # tail
    g.sphere(18, 34, 13, 11, "bay", bias=-0.04)                # rump
    g.sphere(32, 35, 14, 10, "bay")                            # barrel
    g.sphere(45, 34, 10, 10, "bay", bias=0.02)                 # chest
    g.slab([(38, 26), (49, 11), (57, 14), (47, 33)], "bay", t0=0.30, t1=0.86)
    g.slab([(50, 8), (63, 13), (60, 22), (48, 17)], "bay", t0=0.36, t1=0.94)
    g.sphere(62, 19, 5, 4, "bay", bias=0.06)                   # muzzle
    g.slab([(51, 2), (55, 2), (54, 9), (50, 9)], "bay", t0=0.42, t1=0.82)
    g.slab([(57, 3), (61, 4), (59, 10), (55, 9)], "bay", t0=0.38, t1=0.78)
    g.put(57, 15, OUTLINE); g.put(58, 15, OUTLINE)             # eye
    g.put(61, 21, HA[0])                                        # nostril
    for k in range(12):                                         # mane on the crest
        g.put(41 + k, 27 - k, HA[1]); g.put(42 + k, 27 - k, HA[0])
    # Rider: saddle, torso, helm, plume.
    g.slab([(24, 24), (40, 22), (41, 30), (23, 31)], "leather", t0=0.26, t1=0.70)
    g.rod(30, 24, 28, 36, 4, "steel", bias=-0.16)
    g.slab([(24, 8), (38, 6), (41, 24), (23, 25)], "silk", t0=0.30, t1=0.84)
    g.sphere(32, 3, 8, 8, "steel", bias=0.06)
    g.slab([(30, -4), (41, -9), (38, 0), (32, 2)], "gold", t0=0.44, t1=0.96)
    g.rod(36, 12, 52, 20, 2, "wood", bias=0.06)                # lance across the saddle
    edge(g)
    return g
