import sys
sys.path.insert(0, ".")
from raster import Grid

INK, PAPER = "#100E18", "#F2E7D0"
RED, GOLD, BLUE = "#E23140", "#F5B325", "#2B4FD9"
SKY, SKY2, GROUND = "#241F3D", "#39305C", "#171327"

W, H = 210, 78
HZ = 64


def knight(g, ox, oy, flip, plume, shield):
    """A mounted knight as one silhouette. Only the outline has to be right."""
    def X(x):
        return ox + (68 - x) if flip else ox + x

    def ell(cx, cy, rx, ry, v=INK):
        g.ellipse(X(cx), oy + cy, rx, ry, v)

    def poly(pts, v=INK):
        g.poly([(X(px), oy + py) for px, py in pts], v)

    def bar(x0, y0, x1, y1, w, v=INK):
        g.bar(X(x0), oy + y0, X(x1), oy + y1, w, v)

    # Legs first, so the body masses close over their tops.
    bar(44, 32, 58, 48, 4); bar(58, 48, 57, 55, 4)
    bar(40, 32, 45, 50, 4); bar(45, 50, 44, 55, 4)
    bar(14, 32, 3, 46, 4);  bar(3, 46, 3, 55, 4)
    bar(20, 34, 13, 50, 4); bar(13, 50, 12, 55, 4)
    poly([(6, 24), (0, 28), (1, 42), (9, 31)])          # tail
    ell(16, 30, 12, 10); ell(30, 31, 13, 9); ell(43, 30, 9, 9)
    poly([(37, 21), (48, 9), (56, 14), (44, 30)])       # neck
    poly([(51, 5), (66, 11), (64, 19), (49, 15)])       # head
    poly([(53, 2), (57, 2), (56, 7), (52, 7)])          # ear
    ell(65, 15, 3, 3)                                    # muzzle
    # Rider.
    bar(27, 20, 25, 33, 5)
    poly([(21, 5), (34, 3), (37, 20), (22, 22)])         # torso
    ell(29, 0, 6, 6)                                     # helm
    poly([(30, -4), (43, -10), (39, -2), (32, 2)], plume)
    ell(38, 13, 6, 8, shield)


def scene():
    g = Grid(W, H)
    g.rect(0, 0, W, 26, SKY)
    g.rect(0, 26, W, HZ - 26, SKY2)
    g.ellipse(105, 38, 38, 30, GOLD)                     # the sun
    for i, bx in enumerate(range(8, W - 6, 26)):         # crowd banners, behind
        c = RED if i % 2 else BLUE
        g.bar(bx, HZ - 20, bx, HZ - 1, 2, INK)
        g.poly([(bx + 1, HZ - 20), (bx + 10, HZ - 17), (bx + 1, HZ - 13)], c)
    g.rect(0, HZ, W, H - HZ, GROUND)
    knight(g, 22, 14, False, RED, RED)
    knight(g, 120, 14, True, BLUE, BLUE)
    # Couched on a real diagonal, and stopped short: they have just shattered.
    g.bar(56, 26, 99, 48, 4, PAPER)
    g.bar(154, 26, 111, 48, 4, PAPER)
    g.poly([(76, 36), (88, 31), (78, 43)], RED)          # pennons on the shaft
    g.poly([(134, 36), (122, 31), (132, 43)], BLUE)
    for dx, dy, c in ((-8, -9, PAPER), (7, -11, PAPER), (-12, 1, PAPER), (10, 0, GOLD),
                      (0, -16, PAPER), (14, -6, PAPER), (-16, -5, GOLD), (5, 7, PAPER),
                      (-6, 9, PAPER), (2, -22, GOLD), (-3, 14, PAPER)):
        g.rect(105 + dx, 49 + dy, 2, 2, c)               # splinters
    # The tilt runs between them, not across the foreground.
    g.rect(0, 56, W, 3, INK); g.rect(0, 62, W, 3, INK)
    for px in range(6, W, 20):
        g.rect(px, 54, 3, 13, INK)
    return g


if __name__ == "__main__":
    print(scene().svg(scale=6)[:60])
