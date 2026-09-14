import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixel_marks import *  # noqa: F403,E402

# Write beside this file, not into whatever directory it was run from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------- Main hero
W, H, HORIZON = 160, 48, 34
p = DUSK
r = sky(W, H, p, HORIZON)
r += pennant(45, 11, 23, p) + pennant(141, 9, 25, p, flag=p["tincture"])
r += barrier(0, HORIZON + 4, W, p)
r += [(0, HORIZON + 10, W, 4, p["dirt"]), (0, HORIZON + 12, W, 2, p["dirt2"])]
r += shield(13, 5, p)
r += word(62, 12, p["gold"], shadow=p["ink"])

hero = f"""<div style="position: relative; width: 1280px; height: 384px; background: {p['sky0']}; overflow: hidden">
  <div class="pixel" style="position: absolute; inset: 0">{svg(r, W, H)}</div>
  <div class="type" style="position: absolute; left: 496px; top: 232px; color: {p['parch']}; font-size: 19px; letter-spacing: 1px">Drop a competition. Joust it.</div>
  <div class="type" style="position: absolute; left: 497px; top: 60px; color: {p["steel"]}; font-size: 13px; letter-spacing: 3px">A PERSISTENT AUTONOMOUS COMPETITION AGENT</div>
</div>"""
artboard("Main.dc.html", 1280, 384, hero)

# ---------------------------------------------------------- Agent Index card
CW, CH, CHZ = 150, 75, 54
r = sky(CW, CH, p, CHZ)
r += pennant(16, 22, 32, p) + pennant(132, 20, 34, p, flag=p["tincture"])
r += barrier(0, CHZ + 5, CW, p)
r += [(0, CHZ + 12, CW, 5, p["dirt"]), (0, CHZ + 15, CW, 3, p["dirt2"])]
r += shield(59, 6, p)
r += word(int((CW - WORD_W) / 2), 50, p["gold"], shadow=p["ink"])

card = f"""<div style="position: relative; width: 1200px; height: 600px; background: {p['sky0']}; overflow: hidden">
  <div class="pixel" style="position: absolute; inset: 0">{svg(r, CW, CH)}</div>
  <div class="type" style="position: absolute; left: 0; right: 0; top: 520px; text-align: center; color: {p['parch']}; font-size: 22px; letter-spacing: 1px">Drop a competition. Joust it.</div>
</div>"""
artboard("IndexCard.dc.html", 1200, 600, card)

# ------------------------------------------------------------- Icon / crest set
names = ["shield", "lance", "pennant", "helm", "barrier", "cup"]
labels = {"shield": "crest", "lance": "lance", "pennant": "pennant",
          "helm": "helm", "barrier": "tilt", "cup": "prize"}
cells = []
for n in names:
    art = [(x, y, w, h, c) for x, y, w, h, c in ICONS[n](p)]
    cells.append(f"""<div style="display: flex; flex-direction: column; align-items: center; gap: 14px">
      <div class="pixel" style="width: 96px; height: 96px">{svg(art, 16, 16)}</div>
      <div class="pixel" style="width: 32px; height: 32px">{svg(art, 16, 16)}</div>
      <div class="type" style="color: {p['steel']}; font-size: 12px; letter-spacing: 2px">{labels[n].upper()}</div>
    </div>""")

crest_big = svg(shield(0, 0, p), 32, 38)
sheet = f"""<div style="width: 1040px; height: 560px; background: {p['sky0']}; padding: 44px 48px; box-sizing: border-box; display: flex; flex-direction: column; gap: 36px">
  <div style="display: flex; align-items: center; gap: 28px">
    <div class="pixel" style="width: 118px; height: 140px">{crest_big}</div>
    <div style="display: flex; flex-direction: column; gap: 10px">
      <div class="type" style="color: {p['gold']}; font-size: 26px; letter-spacing: 3px">JOUST MARKS</div>
      <div class="type" style="color: {p['steel']}; font-size: 13px; letter-spacing: 1px; max-width: 520px; line-height: 1.9">Per pale crimson and azure, a lance in pale gold. Every mark is drawn on a 16&nbsp;pixel grid and keeps its shape down to a favicon.</div>
    </div>
  </div>
  <div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 24px; align-items: start">
    {''.join(cells)}
  </div>
  <div style="display: flex; gap: 14px; align-items: center">
    {''.join(f'<div style="display:flex;flex-direction:column;gap:8px;align-items:center"><div style="width:56px;height:34px;background:{p[k]}"></div><div class="type" style="color:{p["steel2"]};font-size:10px">{k}</div></div>' for k in ["crimson","gold","sky1","parch","steel","field","dirt","ink"])}
  </div>
</div>"""
artboard("Crests.dc.html", 1040, 560, sheet)


# ------------------------------------------------------------- direction sketches
def sketch(path, palette, label, note, width, starry=True, counterchange=False):
    q = palette
    sw, sh, hz = 160, 50, 36
    rr = sky(sw, sh, q, hz, starry=starry)
    rr += barrier(0, hz + 5, sw, q)
    rr += shield(13, 6, q, counterchange=counterchange)
    rr += word(62, 14, q["gold"], shadow=q["ink"] if q is not PARCH else None)
    body = f"""<div style="position: relative; width: {width}px; height: {int(width * sh / sw)}px; background: {q['sky0']}; overflow: hidden">
      <div class="pixel" style="position: absolute; inset: 0">{svg(rr, sw, sh)}</div>
      <div class="type" style="position: absolute; left: {int(width * 62 / sw)}px; top: {int(width * 32 / sw)}px; color: {q['parch']}; font-size: 13px; letter-spacing: 1px">Drop a competition. Joust it.</div>
    </div>
    <div style="width: {width}px; padding: 14px 2px 0; box-sizing: border-box; display: flex; flex-direction: column; gap: 6px">
      <div class="type" style="color: #8a8aa0; font-size: 13px; letter-spacing: 2px">{label}</div>
      <div style="font-family: 'Courier New', monospace; color: #6f6f86; font-size: 12px; line-height: 1.6">{note}</div>
    </div>"""
    artboard(path, width, 0, f'<div style="background:#0e0d15;padding:20px;display:inline-block">{body}</div>')


sketch("DirectionB.dc.html", PARCH, "B · TOURNAMENT ROLL",
       "Two inks on parchment, like a heraldic roll of arms.<br>Reads on any background and prints flat.<br>Tradeoff: no night drama, and it can look dry beside<br>the coloured agent cards on the index.", 620,
       starry=False, counterchange=True)
sketch("DirectionC.dc.html", ARCADE, "C · ARCADE LISTS",
       "NES palette, pure black ground, high-saturation.<br>Loudest at thumbnail size on a crowded index page.<br>Tradeoff: reads as a game, not as an agent that does<br>real engineering work.", 620)

canvas = {
    "artboards": [
        {"file": "Main.dc.html", "x": 0, "y": 0, "w": 1280, "h": 384},
        {"file": "IndexCard.dc.html", "x": 1400, "y": 0, "w": 1200, "h": 600},
        {"file": "Crests.dc.html", "x": 0, "y": 520, "w": 1040, "h": 560},
        {"file": "DirectionB.dc.html", "x": 0, "y": 1220, "w": 660, "h": 340},
        {"file": "DirectionC.dc.html", "x": 780, "y": 1220, "w": 660, "h": 340},
    ],
    "annotations": [
        {"id": "brief", "x": 0, "y": -200, "w": 520,
         "text": "JOUST — pixel-art identity\nDirection A (built): dusk tournament field, per-pale crest, hand-drawn pixel wordmark.\nB and C below are low-fi alternates. Say which one and I build the set in it."},
        {"id": "hero-note", "x": 1400, "y": 700, "w": 420,
         "text": "Hero is 1280x384 (10:3) for the README.\nCard is 1200x632 for the Agent Index and link previews.\nExport either as PNG from the artboard toolbar."},
    ],
    "launch": {"view": "canvas"},
}
with open("canvas.json", "w", encoding="utf-8") as fh:
    json.dump(canvas, fh, indent=2)
print("artboards:", sorted(f for f in os.listdir('.') if f.endswith('.dc.html')))


# Standalone pages the PNG renderer captures, so the exported images are
# reproducible rather than hand-exported from a design tool.
import re as _re

_css = _re.search(r"<style>(.*?)</style>", open("Main.dc.html", encoding="utf-8").read(), _re.S).group(1)
_font = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Silkscreen:wght@400;700&display=swap">')
for _src, _out in (("Main.dc.html", "shot-hero.html"), ("IndexCard.dc.html", "shot-card.html")):
    _body = open(_src, encoding="utf-8").read().split("</helmet>")[1].split("</x-dc>")[0]
    with open(_out, "w", encoding="utf-8") as _fh:
        _fh.write(f'<!doctype html><meta charset="utf-8">{_font}'
                  f"<style>{_css} html,body{{margin:0;padding:0}}</style>{_body}")
print("render pages: shot-hero.html, shot-card.html")
