"""Small standing and seated figures for the tournament scenes."""
import sys
sys.path.insert(0, ".")

INK, PAPER = "#100E18", "#F2E7D0"
RED, GOLD, BLUE, GREEN = "#E23140", "#F5B325", "#2B4FD9", "#2C8C5A"
SKY, SKY2, GROUND = "#241F3D", "#39305C", "#171327"
TIMBER, TIMBER2 = "#5A3B24", "#7A5233"


def crown(g, cx, cy, w, v=GOLD):
    g.rect(cx - w // 2, cy, w, 2, v)
    for i in range(3):
        g.rect(cx - w // 2 + i * (w // 2 - 1), cy - 2, 2, 2, v)


def seated(g, cx, feet, robe, *, crowned=False, hand=None, head=PAPER):
    """A figure on a bench: robe, shoulders, head, optional crown and gift."""
    top = feet - 20
    g.poly([(cx - 7, top + 8), (cx + 7, top + 8), (cx + 9, feet), (cx - 9, feet)], robe)
    g.poly([(cx - 6, top + 4), (cx + 6, top + 4), (cx + 7, top + 10), (cx - 7, top + 10)], robe)
    g.ellipse(cx, top, 4, 5, head)
    g.ellipse(cx, top - 2, 4, 3, INK)                      # hair
    if crowned:
        crown(g, cx, top - 6, 9)
    if hand:
        g.bar(cx + 6, top + 8, cx + 13, top + 12, 2, robe)
        g.ellipse(cx + 15, top + 13, 3, 3, hand)


def standing(g, cx, feet, robe, *, head=PAPER, helm=None, reach=None, hair=INK):
    h = feet - 34
    g.bar(cx - 4, feet - 15, cx - 4, feet, 4, INK)
    g.bar(cx + 4, feet - 15, cx + 4, feet, 4, INK)
    g.poly([(cx - 7, h + 8), (cx + 7, h + 8), (cx + 9, feet - 13), (cx - 9, feet - 13)], robe)
    g.poly([(cx - 6, h + 4), (cx + 6, h + 4), (cx + 7, h + 10), (cx - 7, h + 10)], robe)
    g.ellipse(cx, h, 4, 5, head)
    g.ellipse(cx, h - 2, 4, 3, hair)
    if reach:
        g.bar(cx + 6, h + 8, reach[0], reach[1], 3, robe)
        g.ellipse(reach[0], reach[1], 3, 3, head)
    if helm:
        # Carried in the crook of the arm: the point of the scene is a bare head.
        g.ellipse(cx - 12, h + 13, 6, 7, helm)
        g.rect(cx - 17, h + 12, 11, 2, INK)                 # visor slot
        g.bar(cx - 7, h + 9, cx - 12, h + 11, 4, robe)


def stand_frame(g, x0, x1, deck, roof, *, cloth=RED):
    """The timber gallery the royal party sits in."""
    g.rect(x0, deck, x1 - x0, 4, TIMBER2)
    g.rect(x0, deck + 4, x1 - x0, 3, TIMBER)
    for px in range(x0 + 4, x1, 20):
        g.rect(px, deck + 7, 4, 30, TIMBER)
    g.rect(x0 - 3, roof, x1 - x0 + 6, 5, TIMBER)
    for i, px in enumerate(range(x0 - 3, x1 + 3, 10)):       # scalloped valance
        c = cloth if i % 2 else GOLD
        g.poly([(px, roof + 5), (px + 10, roof + 5), (px + 5, roof + 12)], c)
    g.rect(x0, roof + 12, x1 - x0, deck - roof - 12, "#1C1830")
    for px in range(x0 + 6, x1 - 6, 26):                     # hanging drapes
        g.rect(px, roof + 12, 7, deck - roof - 12, cloth)
