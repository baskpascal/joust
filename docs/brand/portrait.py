"""A knight's bust, close up: every mass lit, nothing a flat silhouette."""
import sys
sys.path.insert(0, ".")
from shade import OUTLINE, RAMPS, Shade, pick

W, H = 96, 100
S = RAMPS["steel"]
G = RAMPS["gold"]
R = RAMPS["red"]


def outline(g, colour=OUTLINE):
    """One dark pixel wherever the figure meets the ground."""
    filled = [[c is not None for c in row] for row in g.cells]
    for y in range(g.h):
        for x in range(g.w):
            if filled[y][x] or not any(
                0 <= y + dy < g.h and 0 <= x + dx < g.w and filled[y + dy][x + dx]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                continue
            g.put(x, y, colour)


def backdrop(g):
    d = RAMPS["dusk"]
    for y in range(H):
        for x in range(W):
            k = 0.92 - (y / H) * 0.45
            k -= (abs(x - W / 2) / (W / 2)) ** 2 * 0.34      # vignette
            g.put(x, y, pick(d, k, x, y))
    for bx in (10, 82):                                       # banners behind
        g.slab([(bx - 4, 8), (bx + 4, 8), (bx + 4, 62), (bx - 4, 62)], "red",
               t0=0.10, t1=0.34)
        g.slab([(bx - 5, 4), (bx + 5, 4), (bx + 5, 9), (bx - 5, 9)], "wood",
               t0=0.14, t1=0.32)


def bust(g):
    # Mail first, so the plate sits on top of it.
    g.mail(20, 86, 56, 36, "steel")
    # One shoulder mass each, divided into lames by lines that follow its curve.
    for cx, flip in ((15, 1), (81, -1)):
        rx, ry, cy = 23, 15, 100
        g.sphere(cx, cy, rx, ry, "steel", bias=-0.05)
        for k in range(-rx, rx + 1):                          # lit leading edge
            off = (1 - (k / (rx + 0.5)) ** 2) ** 0.5
            g.put(cx + k, cy - int(off * ry), S[4])
            g.put(cx + k, cy - int(off * ry) + 1, S[3])
        for band, tone in ((0.34, S[0]), (0.72, S[0])):       # lame divisions
            for k in range(-rx, rx + 1):
                off = (1 - (k / (rx + 0.5)) ** 2) ** 0.5
                yy = cy - int(off * ry) + int(band * 2 * off * ry)
                if abs(k) > rx - 2:
                    continue
                g.put(cx + k, yy, tone)
                g.put(cx + k, yy + 1, S[3])
        for i, rxx in enumerate((-13, -1, 11)):               # rivets
            g.put(cx + flip * rxx, cy - 4 + i, S[4])
            g.put(cx + flip * rxx + 1, cy - 3 + i, S[0])
    g.slab([(34, 100), (62, 100), (68, 122), (28, 122)], "red", t0=0.28, t1=0.70)
    g.slab([(44, 100), (52, 100), (54, 122), (42, 122)], "gold", t0=0.42, t1=0.88)
    for py in range(102, 122, 5):
        g.put(45, py, G[4]); g.put(51, py + 2, G[1])

    # Gorget: a clean banded collar, not a lump.
    g.slab([(27, 84), (69, 84), (72, 94), (24, 94)], "steel", t0=0.26, t1=0.78)
    g.slab([(27, 84), (69, 84), (69, 87), (27, 87)], "steel", t0=0.70, t1=1.0)
    for rx in range(30, 68, 6):
        g.put(rx, 90, S[4]); g.put(rx + 1, 91, S[0])

    # The helm: dome, face, chin, then the reinforce raised over all of it.
    g.sphere(48, 38, 22, 26, "steel")
    g.slab([(27, 40), (69, 40), (65, 82), (31, 82)], "steel", t0=0.24, t1=0.74)
    g.slab([(31, 79), (65, 79), (63, 83), (33, 83)], "steel", t0=0.16, t1=0.46)

    # Brow reinforce above the sight, with its own rivet line.
    g.slab([(26, 38), (70, 38), (70, 46), (26, 46)], "steel", t0=0.52, t1=0.98)
    for rx in range(29, 70, 7):
        g.put(rx, 41, S[4]); g.put(rx + 1, 42, S[0])

    # Vertical rib: light face, dark cast edge either side, so it stands proud.
    g.slab([(44, 12), (52, 12), (52, 83), (44, 83)], "steel", t0=0.62, t1=1.0, axis="x")
    for ry in range(13, 84):
        g.put(43, ry, S[0]); g.put(53, ry, S[1])
    for ry in range(18, 82, 9):
        g.put(45, ry, S[4]); g.put(51, ry + 1, S[0])

    # Ocularium: dark slot, lit lower lip, shadow above.
    for x0, x1 in ((28, 42), (54, 68)):
        for y in range(47, 53):
            for x in range(x0, x1):
                g.put(x, y, OUTLINE if y < 51 else S[1])
        for x in range(x0, x1):
            g.put(x, 53, S[3])
            g.put(x, 46, S[0])

    # Breaths, symmetric, each with a highlight under the rim.
    for cx, cy in ((33, 62), (39, 68), (33, 70), (29, 64),
                   (61, 62), (55, 68), (61, 70), (65, 64)):
        g.put(cx, cy, OUTLINE); g.put(cx + 1, cy, OUTLINE)
        g.put(cx, cy + 1, S[3])

    # Wear on the lit rim, and a scratch across the shadowed cheek.
    for x, y in ((32, 24), (33, 22), (36, 19), (40, 17), (30, 30), (29, 34), (31, 27)):
        g.put(x, y, S[4])
    for i in range(8):
        g.put(57 + i, 30 + (i >> 1), S[1])


def plume(g):
    """Five overlapping strands, so it reads as a crest and not as flames."""
    strands = ((-10, "gold", -5), (-5, "red", -2), (0, "red", 0),
               (5, "gold", 3), (10, "red", 6))
    for dx, ramp, lean in strands:
        base = 48 + dx
        for k in range(18):
            wsp = max(2, 9 - k // 3)
            x = base + lean * k // 7
            y = 15 - k
            if y < 0:
                break
            t = 0.26 + k * 0.042
            for xx in range(x - wsp // 2, x - wsp // 2 + wsp):
                g.put(xx, y, pick(RAMPS[ramp], t + (xx - x) * 0.055, xx, y))


def portrait():
    g = Shade(W, H)
    backdrop(g)
    figure = Shade(W, H)
    plume(figure)
    bust(figure)
    outline(figure)
    for y in range(H):
        for x in range(W):
            if figure.cells[y][x] is not None:
                g.cells[y][x] = figure.cells[y][x]
    return g
