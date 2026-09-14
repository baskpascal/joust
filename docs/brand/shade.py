"""Shaded pixel art: colour ramps, a light direction, ordered dithering.

Flat silhouettes hide the fact that nothing is modelled. Here every mass is
lit: a ramp per material, a normal per pixel, and a 2x2 ordered dither at the
band boundaries so the steps read as gradation instead of banding.
"""
import math
import sys

sys.path.insert(0, ".")
from raster import Grid

# Five steps each: shadow core, shadow, base, light, specular.
RAMPS = {
    "steel":   ["#171C2B", "#333E55", "#5F6E8B", "#94A6C2", "#DCE7F7"],
    "gold":    ["#3F2710", "#7A5016", "#B87F1F", "#EFB53C", "#FFE79B"],
    "red":     ["#33101A", "#661726", "#A32437", "#D44050", "#EE8287"],
    "blue":    ["#0E1738", "#1C2B66", "#304796", "#4F6CCB", "#8FA4F0"],
    "skin":    ["#43201A", "#733D28", "#A35D3C", "#CB8963", "#EFBB94"],
    "leather": ["#221510", "#40281B", "#66442B", "#8C6440", "#B08A60"],
    "wood":    ["#1F130F", "#3B2419", "#5E3D28", "#84603E", "#A6825A"],
    "bay":     ["#160E12", "#31201C", "#553326", "#7B4C36", "#A67152"],
    "dusk":    ["#12101F", "#1E1B33", "#2E2848", "#443A63", "#5E4E7E"],
    "dawn":    ["#3B2E4A", "#6B4A5C", "#A8706A", "#DCA07C", "#F7D6A6"],
    "torch":   ["#4A1A08", "#8C3A0C", "#CC6A14", "#F0A32C", "#FFE08A"],
    "silk":    ["#2E0A14", "#5E1220", "#9E1E33", "#D43A52", "#F4808E"],
    "mist":    ["#3A3552", "#4E4668", "#665C82", "#82779C", "#A296B6"],
    "hair":    ["#140D10", "#2A1A18", "#452B22", "#63422F", "#85603F"],
}
OUTLINE = "#0E0A16"

_DITHER = ((0.30, 0.72), (0.94, 0.52))


def pick(ramp, t, x, y):
    """A ramp step for brightness t, dithered across the boundary."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    f = t * (len(ramp) - 1)
    i = int(f)
    if i >= len(ramp) - 1:
        return ramp[-1]
    return ramp[i + 1] if (f - i) > _DITHER[y & 1][x & 1] else ramp[i]


class Shade(Grid):
    light = (-0.46, -0.68, 0.57)

    def sphere(self, cx, cy, rx, ry, ramp, *, bias=0.0, gain=1.0, squash=1.0):
        """A lit ellipsoid: the workhorse for helms, shoulders, rumps."""
        lx, ly, lz = self.light
        colours = RAMPS[ramp]
        for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
                u, v = (x - cx) / rx, (y - cy) / ry
                r2 = u * u + v * v
                if r2 > 1.0:
                    continue
                z = math.sqrt(max(0.0, 1.0 - r2)) * squash
                t = (u * lx + v * ly + z * lz) * gain + bias
                self.put(x, y, pick(colours, t, x, y))

    def rod(self, x0, y0, x1, y1, r, ramp, *, bias=0.0, gain=1.0):
        """A lit cylinder: lances, limbs, poles, rails."""
        lx, ly, lz = self.light
        colours = RAMPS[ramp]
        dx, dy = x1 - x0, y1 - y0
        length = max(1e-6, math.hypot(dx, dy))
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        for i in range(int(length * 3) + 1):
            t = i / (length * 3)
            cx, cy = x0 + dx * t, y0 + dy * t
            for k in range(-r, r + 1):
                n = k / r
                z = math.sqrt(max(0.0, 1.0 - n * n))
                d = (px * n * lx + py * n * ly + z * lz) * gain + bias
                self.put(int(round(cx + px * k)), int(round(cy + py * k)),
                         pick(colours, d, int(round(cx + px * k)), int(round(cy + py * k))))

    def slab(self, pts, ramp, *, t0=0.30, t1=0.95, axis="x"):
        """A flat plane lit by a linear gradient — bands, straps, planks."""
        colours = RAMPS[ramp]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lo, hi = (min(xs), max(xs)) if axis == "x" else (min(ys), max(ys))
        span = max(1, hi - lo)
        mask = Grid(self.w, self.h)
        mask.poly(pts, 1)
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            for x in range(max(0, min(xs)), min(self.w, max(xs) + 1)):
                if mask.cells[y][x] is None:
                    continue
                k = ((x if axis == "x" else y) - lo) / span
                self.put(x, y, pick(colours, t0 + (t1 - t0) * k, x, y))

    def mail(self, x0, y0, w, h, ramp, *, clip=None):
        """Riveted mail: a two-tone weave, offset row by row."""
        colours = RAMPS[ramp]
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                if clip and clip.cells[y][x] is None:
                    continue
                on = ((x + (y & 1)) >> 1) & 1
                self.put(x, y, colours[2 if on else 1])

    def glow(self, cx, cy, r, ramp, strength=0.95):
        """A dithered bloom, so torchlight falls off in pixels not in blur."""
        colours = RAMPS[ramp]
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                d = math.hypot(x - cx, y - cy) / r
                if d > 1.0:
                    continue
                dens = (1.0 - d) ** 2 * strength
                if dens > _DITHER[y & 1][x & 1]:
                    self.put(x, y, colours[4] if dens > 0.78 else colours[3])

    def rim(self, pts, ramp_or_hex, width=1):
        """Selective outline: the edge, not a uniform black keyline."""
        colour = ramp_or_hex if ramp_or_hex.startswith("#") else RAMPS[ramp_or_hex][0]
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            self.bar(x0, y0, x1, y1, width, colour)

    def speck(self, x, y, colour):
        self.put(x, y, colour)
