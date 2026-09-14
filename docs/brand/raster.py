"""Rasterise shapes onto a pixel grid.

Hand-typed ASCII gave slabs where a horse should be, because a silhouette is
made of overlapping organic masses, not rectangles. Ellipses and polygons
snapped to the grid give the outline; nothing is anti-aliased.
"""


class Grid:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[None] * w for _ in range(h)]

    def put(self, x, y, v):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = v

    def ellipse(self, cx, cy, rx, ry, v):
        for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    self.put(x, y, v)

    def poly(self, pts, v):
        ys = [p[1] for p in pts]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            for i in range(len(pts)):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % len(pts)]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(int(round(xs[i])), int(round(xs[i + 1])) + 1):
                    self.put(x, y, v)

    def bar(self, x0, y0, x1, y1, w, v):
        """A thick segment, stamped square so the ends stay chunky."""
        steps = max(abs(x1 - x0), abs(y1 - y0)) * 3 + 1
        for i in range(steps + 1):
            t = i / steps
            cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for dy in range(-(w // 2), w - w // 2):
                for dx in range(-(w // 2), w - w // 2):
                    self.put(int(round(cx)) + dx, int(round(cy)) + dy, v)

    def rect(self, x, y, w, h, v):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.put(xx, yy, v)

    def rects(self):
        out = []
        for y, row in enumerate(self.cells):
            x = 0
            while x < self.w:
                v = row[x]
                if v is None:
                    x += 1
                    continue
                run = 1
                while x + run < self.w and row[x + run] == v:
                    run += 1
                out.append((x, y, run, v))
                x += run
        return out

    def svg(self, *, scale=None, style="", label=""):
        body = "".join(f'<rect x="{x}" y="{y}" width="{r}" height="1" fill="{v}"/>'
                       for x, y, r, v in self.rects())
        px = f"width: {self.w * scale}px; height: {self.h * scale}px;" if scale else ""
        return (f'<svg viewBox="0 0 {self.w} {self.h}" style="{px} display: block; '
                f'image-rendering: pixelated;{style}" shape-rendering="crispEdges" '
                f'role="img" aria-label="{label}">{body}</svg>')
