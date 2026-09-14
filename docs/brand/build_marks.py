import os
import sys

# Runs from anywhere; writes beside itself.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from marks import *  # noqa: E402,F403

INK, PAPER = "#100E18", "#F2E7D0"
RED, GOLD, BLUE, GREEN = "#E23140", "#F5B325", "#2B4FD9", "#2C8C5A"
STEEL, STEEL_D = "#A8B8D8", "#63739B"

FONT = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&amp;'
        'family=Space+Grotesk:wght@500;700&amp;family=JetBrains+Mono:wght@700&amp;display=swap">')
CSS = """
    body { margin: 0; background: %s; }
    .display { font-family: 'Archivo Black', 'Helvetica Neue', Helvetica, sans-serif; }
    .body { font-family: 'Space Grotesk', 'Helvetica Neue', Helvetica, sans-serif; }
    .mono { font-family: 'JetBrains Mono', 'Courier New', monospace; }
    .lbl { font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: 12px; font-weight: 700;
           letter-spacing: 2px; text-transform: uppercase; color: %s; opacity: 0.62; }
    a { color: %s; } a:hover { color: %s; }
""" % (PAPER, INK, RED, BLUE)


def board(path, inner):
    open(path, "w", encoding="utf-8").write(
        "<!doctype html>\n<html>\n<head>\n  <meta charset=\"utf-8\">\n"
        "  <script src=\"./support.js\"></script>\n</head>\n<body>\n<x-dc>\n<helmet>\n  "
        + FONT + "\n  <style>" + CSS + "  </style>\n</helmet>\n" + inner
        + "\n</x-dc>\n</body>\n</html>\n")


def helm(scale, *, steel=STEEL, crest=RED, crest2=GOLD, band=PAPER, style=""):
    return svg(HELM, {"K": INK, "S": steel, "B": band, "E": INK, "c": crest, "d": crest2},
               scale=scale, style=style, label="Joust helm")


def shield(scale, field, charge, charge_colour, *, style=""):
    s = svg(SHIELD, {"K": INK, "f": field}, scale=scale, label="shield")
    c = svg(CHARGES[charge], {"g": charge_colour}, scale=scale,
            style=" position: absolute; left: 0; top: %dpx;" % (scale * 3))
    return (f'<div style="position: relative; width: {16 * scale}px;{style}">{s}{c}</div>')


def icon(art, scale, extra=None):
    ink = {"K": INK, "g": GOLD, "w": PAPER, "r": RED}
    ink.update(extra or {})
    return svg(art, ink, scale=scale)


# ------------------------------------------------------------------- Main
mark, _ = wordmark("JOUST", [(2, 2, BLUE), (1, 1, RED), (0, 0, INK)], h=150)
board("Main.dc.html", f"""
<div style="position: relative; width: 1280px; height: 420px; background: {PAPER}; border: 9px solid {INK}; box-sizing: border-box; overflow: hidden; display: flex; align-items: center; gap: 54px; padding: 0 56px">
  <div style="position: relative; display: flex; flex-direction: column; gap: 26px; flex: 1">
    {mark}
    <div style="display: flex; flex-direction: column; gap: 14px">
      <div class="body" style="font-size: 27px; font-weight: 700; color: {INK}">Drop a competition. Joust it.</div>
      <div style="display: flex; align-items: center; gap: 12px">
        <div style="width: 72px; height: 11px; background: {RED}; border: 3px solid {INK}; box-sizing: border-box"></div>
        <div class="body" style="font-size: 15px; font-weight: 500; color: {INK}; letter-spacing: 3px; text-transform: uppercase">A persistent autonomous competition agent</div>
      </div>
    </div>
  </div>
  <div style="flex: none">{helm(13)}</div>
</div>""")

# ------------------------------------------------------------------- Card
cmark, _ = wordmark("JOUST", [(2, 2, BLUE), (1, 1, RED), (0, 0, INK)], h=126)
board("Card.dc.html", f"""
<div style="position: relative; width: 1200px; height: 630px; background: {PAPER}; border: 10px solid {INK}; box-sizing: border-box; overflow: hidden; display: flex; align-items: center; gap: 56px; padding: 0 66px">
  <div style="position: relative; flex: none; width: 294px; height: 336px">
    <div style="position: absolute; left: -18px; top: 42px; width: 282px; height: 282px; border-radius: 50%; background: {GOLD}; border: 9px solid {INK}; box-sizing: border-box"></div>
    <div style="position: absolute; left: 0; top: 0">{helm(14)}</div>
  </div>
  <div style="position: relative; display: flex; flex-direction: column; gap: 26px">
    {cmark}
    <div class="body" style="font-size: 29px; font-weight: 700; color: {INK}">Drop a competition. Joust it.</div>
    <div style="display: flex; align-items: center; gap: 12px">
      <div style="width: 72px; height: 11px; background: {RED}; border: 3px solid {INK}; box-sizing: border-box"></div>
      <div class="body" style="font-size: 15px; font-weight: 500; color: {INK}; letter-spacing: 3px; text-transform: uppercase">Autonomous competition agent</div>
    </div>
  </div>
</div>""")

# ------------------------------- shaded scenes, as images rather than vectors
import png as _png  # noqa: E402
from portrait import portrait as _portrait  # noqa: E402
from scenes2 import favour as _favour, prize as _prize, rider as _rider  # noqa: E402
from duel import scene as _duel_scene  # noqa: E402

IMG_TPL = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>
    body {{ margin: 0; background: {bg}; }}
    a {{ color: #E23140; }} a:hover {{ color: #2B4FD9; }}
  </style>
</helmet>
<div style="width: {w}px; height: {h}px; background: {bg}; overflow: hidden">
  <img src="{src}" alt="{alt}" style="width: {w}px; height: {h}px; display: block; image-rendering: pixelated" />
</div>
</x-dc>
</body>
</html>
"""

# Dithering alternates colour every pixel, so run-length SVG cannot merge:
# one scene became 5,468 rect nodes and the preview stopped answering.
_scenes = (("Portrait", "portrait", _portrait(), 7, 6, "#12101F", "A knight's helm, close up"),
           ("Prize", "prize", _prize(), 6, 5, "#12101F",
            "The victor takes the prize from the royal stand"),
           ("Favour", "favour", _favour(), 6, 6, "#6B4A5C",
            "A lady knots her favour onto a lance"),
           ("Duel", "duel", _duel_scene(), 6, 6, "#100E18",
            "Two knights colliding at the tilt"))
for name, stem, grid, board_scale, readme_scale, bg, alt in _scenes:
    _png.write(f"{stem}.png", grid)
    _png.write(f"joust-{stem}.png", grid, scale=readme_scale)
    open(f"{name}.dc.html", "w", encoding="utf-8").write(IMG_TPL.format(
        w=grid.w * board_scale, h=grid.h * board_scale, bg=bg, src=f"{stem}.png", alt=alt))

# ---------------------------------------------------------------- Knights
KNIGHTS = [
    ("WILLIAM MARSHAL", "c.1147 – 1219", GOLD, "pale", GREEN, RED, GOLD,
     "Made his name on the Anglo-French tournament circuit, taking horses and ransoms; ended as regent of England."),
    ("RICHARD I", "1157 – 1199", RED, "cross", GOLD, GOLD, PAPER,
     "Tournaments were suppressed in England under the Norman kings. In 1194 he licensed them again, at five sites, for a fee."),
    ("ULRICH VON LIECHTENSTEIN", "c.1200 – 1275", BLUE, "fleur", PAPER, PAPER, BLUE,
     "Styrian knight and poet. His Frauendienst tells of riding a tournament tour of the south in costume."),
    ("GEOFFROI DE CHARNY", "c.1300 – 1356", GREEN, "saltire", PAPER, PAPER, GREEN,
     "Wrote the Book of Chivalry, the plainest account of what the tournament was for. Died carrying the royal standard at Poitiers."),
]
panels = "".join(f"""
  <div style="display: flex; flex-direction: column; gap: 16px; border: 4px solid {INK}; background: {PAPER}; padding: 22px 20px">
    <div style="display: flex; align-items: flex-end; gap: 16px; height: 156px">
      <div style="flex: none">{helm(5, steel=STEEL, crest=cr, crest2=cr2)}</div>
      <div style="flex: none">{shield(7, field, charge, cc)}</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 7px">
      <div class="display" style="font-size: 17px; color: {INK}; letter-spacing: -0.3px; line-height: 1.25">{name}</div>
      <div class="mono" style="font-size: 12px; font-weight: 700; color: {RED}; letter-spacing: 1px">{dates}</div>
    </div>
    <div class="body" style="font-size: 13px; font-weight: 500; color: {INK}; line-height: 1.65; opacity: 0.84">{note}</div>
  </div>"""
  for name, dates, field, charge, cc, cr, cr2, note in KNIGHTS)
board("Knights.dc.html", f"""
<div style="width: 1240px; height: 600px; background: {PAPER}; border: 9px solid {INK}; box-sizing: border-box; padding: 40px 44px; display: flex; flex-direction: column; gap: 28px">
  <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; border-bottom: 5px solid {INK}; padding-bottom: 18px">
    <div class="display" style="font-size: 42px; color: {INK}; letter-spacing: -1.4px">THE ROSTER</div>
    <div class="body" style="font-size: 15px; font-weight: 500; color: {INK}; max-width: 560px; text-align: right; line-height: 1.6">Four real figures of the European tournament. The devices are drawn in the period idiom — they are Joust's marks, not reconstructions of anyone's blazon.</div>
  </div>
  <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px">{panels}</div>
</div>""")

# ------------------------------------------------------------------ Icons
ICONS = [("HELM", None), ("LANCE", LANCE), ("SHIELD", "shield"), ("BARRIER", BARRIER),
         ("PENNON", PENNON), ("CROSSED", CROSSED), ("CHAPLET", CHAPLET)]
cells = []
for label, art in ICONS:
    if art is None:
        big, small = helm(5), helm(2)
    elif art == "shield":
        big, small = shield(6, RED, "cross", GOLD), shield(2, RED, "cross", GOLD)
    else:
        big, small = icon(art, 5), icon(art, 2)
    cells.append(f"""
    <div style="display: flex; flex-direction: column; align-items: center; gap: 14px">
      <div style="height: 120px; display: flex; align-items: center">{big}</div>
      <div style="height: 48px; display: flex; align-items: center">{small}</div>
      <div class="lbl">{label}</div>
    </div>""")
board("Icons.dc.html", f"""
<div style="width: 1240px; height: 460px; background: {PAPER}; border: 9px solid {INK}; box-sizing: border-box; padding: 40px 44px; display: flex; flex-direction: column; gap: 28px">
  <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; border-bottom: 5px solid {INK}; padding-bottom: 18px">
    <div class="display" style="font-size: 42px; color: {INK}; letter-spacing: -1.4px">THE MARKS</div>
    <div class="body" style="font-size: 15px; font-weight: 500; color: {INK}; max-width: 520px; text-align: right; line-height: 1.6">Every mark is drawn on a 16-pixel grid, shown here at 5× and at 2×. Nothing is anti-aliased; the pixel is the unit.</div>
  </div>
  <div style="display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 16px; align-items: start">{''.join(cells)}</div>
</div>""")

# ----------------------------------------------------------------- System
sw = "".join(f"""
      <div style="display: flex; flex-direction: column; gap: 9px">
        <div style="height: 96px; background: {hexv}; border: 4px solid {INK}"></div>
        <div class="mono" style="font-size: 13px; font-weight: 700; color: {INK}">{hexv}</div>
        <div class="body" style="font-size: 13px; color: {INK}; opacity: 0.72">{role}</div>
      </div>"""
  for hexv, role in [(RED, "Lance red · the primary"), (GOLD, "Field gold · grounds and discs"),
                     (BLUE, "Register blue · the offset plate"), (GREEN, "Vert · the fourth tincture"),
                     (PAPER, "Paper · the ground"), (INK, "Keyline · every outline")])
board("System.dc.html", f"""
<div style="width: 1240px; height: 720px; background: {PAPER}; border: 9px solid {INK}; box-sizing: border-box; padding: 40px 44px; display: flex; flex-direction: column; gap: 30px">
  <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; border-bottom: 5px solid {INK}; padding-bottom: 18px">
    <div class="display" style="font-size: 42px; color: {INK}; letter-spacing: -1.4px">THE SYSTEM</div>
    <div class="body" style="font-size: 15px; font-weight: 500; color: {INK}; max-width: 540px; text-align: right; line-height: 1.6">Six tinctures, no gradients, no anti-aliasing. Depth comes from off-register plates — the pixel wordmark carries a red and a blue copy one pixel behind the black.</div>
  </div>
  <div style="display: flex; flex-direction: column; gap: 14px">
    <div class="lbl">Tinctures</div>
    <div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px">{sw}</div>
  </div>
  <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px">
    <div style="display: flex; flex-direction: column; gap: 14px">
      <div class="lbl">Type</div>
      <div class="display" style="font-size: 46px; color: {INK}; letter-spacing: -1.6px; line-height: 1">Archivo Black</div>
      <div class="body" style="font-size: 24px; font-weight: 700; color: {INK}">Space Grotesk · Drop a competition.</div>
      <div class="mono" style="font-size: 18px; font-weight: 700; color: {INK}">JetBrains Mono · VERIFIED</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 14px">
      <div class="lbl">Off-register wordmark</div>
      <div style="border: 4px solid {INK}; padding: 22px 24px; display: flex; align-items: center; justify-content: center; background: {PAPER}">
        {wordmark("JOUST", [(2, 2, BLUE), (1, 1, RED), (0, 0, INK)], h=92)[0]}
      </div>
    </div>
  </div>
</div>""")

import json
json.dump({
    "artboards": [
        {"file": "Main.dc.html", "x": 0, "y": 0, "w": 1280, "h": 420},
        {"file": "Card.dc.html", "x": 1400, "y": 0, "w": 1200, "h": 630},
        {"file": "Duel.dc.html", "x": 1400, "y": 790, "w": 1260, "h": 468},
        {"file": "Knights.dc.html", "x": 0, "y": 560, "w": 1240, "h": 600},
        {"file": "Icons.dc.html", "x": 0, "y": 1360, "w": 1240, "h": 460},
        {"file": "System.dc.html", "x": 0, "y": 1960, "w": 1240, "h": 720},
    ],
    "annotations": [
        {"id": "brief", "x": 0, "y": -200, "w": 560,
         "text": "JOUST — pixel identity.\nChunky pixel art on a 16px grid, off-register plates, six tinctures.\nMain is the README hero at 1280x420."}
    ],
    "launch": {"view": "canvas"},
}, open("canvas.json", "w"), indent=2)
print("built:", sorted(f for f in __import__("os").listdir(".") if f.endswith(".dc.html")))


# Standalone pages the PNG renderer captures for the README hero and card.
import re as _re

_css = _re.search(r"<style>(.*?)</style>", open("Main.dc.html", encoding="utf-8").read(), _re.S).group(1)
_font = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&'
         'family=Space+Grotesk:wght@500;700&family=JetBrains+Mono:wght@700&display=swap">')
for _src, _out in (("Main.dc.html", "shot-hero.html"), ("Card.dc.html", "shot-card.html"),
                   ("Icons.dc.html", "shot-marks.html")):
    _body = open(_src, encoding="utf-8").read().split("</helmet>")[1].split("</x-dc>")[0]
    with open(_out, "w", encoding="utf-8") as _fh:
        _fh.write(f'<!doctype html><meta charset="utf-8">{_font}'
                  f"<style>{_css} html,body{{margin:0;padding:0}}</style>{_body}")
print("scenes written as PNG; run render_marks.mjs for the hero, card and marks")
