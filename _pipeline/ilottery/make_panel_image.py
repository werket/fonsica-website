#!/usr/bin/env python3
"""Render the homepage Insights images: North America as a board of raised tiles.

Reads insights/ilottery/atlas.json (built by build_atlas.py), draws the atlas tile map
as a 3D board seen through a camera, in the After Hours palette (teal tiles = eInstants
online), and exports web sizes to images/insights/ilottery/. Two framings: the tall
desktop panel, and a 4:3 inline image for phones that sits on the section's raised band.
Re-run after the data changes.

Usage: python3 _pipeline/ilottery/make_panel_image.py
Needs Playwright (Chromium) for the render and Pillow for the exports.
"""

import json
import math
import os
import tempfile

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ATLAS = os.path.join(REPO, "insights", "ilottery", "atlas.json")
OUT = os.path.join(REPO, "images", "insights", "ilottery")
NAME = "ilottery-atlas-board"

# Framings, in CSS px (rendered at 2x). The panel board fills 68% of the width so it survives
# the cover crop of a narrow 1024 px panel and stays clear of the right-edge fade and the dark
# band behind the caption. The inline board sits on the band colour so its edges disappear.
VARIANTS = [
    {"suffix": "", "W": 1000, "H": 1250, "fit": .68, "x": .48, "y": .43,
     "ground": "#2B292B", "light": ("52%", "34%"), "widths": (800, 1200, 1600, 2000), "jpg": 1600},
    {"suffix": "-inline", "W": 1000, "H": 750, "fit": .88, "x": .5, "y": .5,
     "ground": "#343133", "light": ("50%", "45%"), "widths": (600, 900, 1200), "jpg": 1200},
]
ELEVATION = math.radians(50)  # the camera looks down at the board like a photo of a game board
DISTANCE = 18                 # camera distance from the board centre, in tiles

# Same layout as the atlas page: Canada on row 1, the United States on rows 3 to 10
GRID = {
    "BC": (1, 1), "AB": (2, 1), "SK": (3, 1), "MB": (4, 1), "ON": (6, 1), "QC": (8, 1), "ATL": (10, 1),
    "AK": (1, 3), "ME": (11, 3), "VT": (10, 4), "NH": (11, 4),
    "WA": (1, 5), "ID": (2, 5), "MT": (3, 5), "ND": (4, 5), "MN": (5, 5), "IL": (6, 5), "WI": (7, 5),
    "MI": (8, 5), "NY": (9, 5), "RI": (10, 5), "MA": (11, 5),
    "OR": (1, 6), "NV": (2, 6), "WY": (3, 6), "SD": (4, 6), "IA": (5, 6), "IN": (6, 6), "OH": (7, 6),
    "PA": (8, 6), "NJ": (9, 6), "CT": (10, 6),
    "CA": (1, 7), "UT": (2, 7), "CO": (3, 7), "NE": (4, 7), "MO": (5, 7), "KY": (6, 7), "WV": (7, 7),
    "VA": (8, 7), "MD": (9, 7), "DE": (10, 7),
    "AZ": (2, 8), "NM": (3, 8), "KS": (4, 8), "AR": (5, 8), "TN": (6, 8), "NC": (7, 8), "SC": (8, 8), "DC": (9, 8),
    "OK": (4, 9), "LA": (5, 9), "MS": (6, 9), "AL": (7, 9), "GA": (8, 9),
    "HI": (1, 10), "TX": (4, 10), "FL": (9, 10),
}

TILE = 0.86                   # tile edge in grid units; the rest is the gap
STYLE = {                     # height, top, west face, east face, south face, label colour, label opacity
    "einstants": (0.62, "#2DD4BF", "#25AE9C", "#1F9384", "#197C70", "#103B35", 0.9),
    "online":    (0.34, "#2F6F68", "#29615B", "#24544F", "#1F4A45", "#A9D3CC", 0.7),
    "planned":   (0.34, "#3A3638", "#343133", "#2E2B2D", "#292628", "#ECE7E1", 0.8),
    "offline":   (0.24, "#4A4547", "#403C3E", "#383436", "#322F31", "#A59F99", 0.55),
    "none":      (0.07, "#353133", "#312E30", "#2E2B2D", "#2A2729", "#77716C", 0.6),
}


class Camera:
    """Pinhole camera south of the board centre, looking north and down at it.

    World axes: x east, y south, z up. The camera is centred on x, so screen right is east.
    """

    def __init__(self, cx, cy):
        self.pos = (cx, cy + DISTANCE * math.cos(ELEVATION), DISTANCE * math.sin(ELEVATION))
        fwd = (0.0, -math.cos(ELEVATION), -math.sin(ELEVATION))   # towards the board centre
        self.f = fwd
        self.r = (1.0, 0.0, 0.0)
        self.u = (0.0, -math.sin(ELEVATION), math.cos(ELEVATION))  # r x f, pointing up the screen

    def project(self, x, y, z):
        d = (x - self.pos[0], y - self.pos[1], z - self.pos[2])
        xc = sum(a * b for a, b in zip(d, self.r))
        yc = sum(a * b for a, b in zip(d, self.u))
        zc = sum(a * b for a, b in zip(d, self.f))
        return xc / zc, -yc / zc, zc


def build_svg(tiles, v):
    W, H = v["W"], v["H"]
    boxes = []
    for t in tiles:
        if t["code"] not in GRID:
            continue
        col, row = GRID[t["code"]]
        boxes.append({
            "code": t["code"], "tier": t["tier"], "h": STYLE[t["tier"]][0],
            "x": col - 1,
            "y": 0.0 if row == 1 else row - 3 + 1.45,   # a little air between Canada and the US
        })

    cx = (min(b["x"] for b in boxes) + max(b["x"] for b in boxes) + TILE) / 2
    cy = (min(b["y"] for b in boxes) + max(b["y"] for b in boxes) + TILE) / 2
    cam = Camera(cx, cy)

    pts = [cam.project(b["x"] + dx, b["y"] + dy, dz)
           for b in boxes for dx in (0, TILE) for dy in (0, TILE) for dz in (0, b["h"])]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    scale = W * v["fit"] / (maxx - minx)
    ox = W * v["x"] - scale * (minx + maxx) / 2
    oy = H * v["y"] - scale * (miny + maxy) / 2
    tile_px = scale / cam.project(cx, cy, 0)[2]       # on-screen size of one tile at the centre

    def P(x, y, z):
        a, b, _ = cam.project(x, y, z)
        return ox + scale * a, oy + scale * b

    def poly(points, **attrs):
        d = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
        extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return f'<polygon points="{d}" {extra}/>'

    shadow, glow, body = [], [], []
    far_first = sorted(boxes, key=lambda b: -math.dist(cam.pos, (b["x"] + TILE / 2, b["y"] + TILE / 2, b["h"] / 2)))
    for b in far_first:
        x0, y0, x1, y1, h = b["x"], b["y"], b["x"] + TILE, b["y"] + TILE, b["h"]
        _, top, west, east, south, ink, ink_op = STYLE[b["tier"]]
        shadow.append(poly([P(x0 + .1, y0 + .16, 0), P(x1 + .1, y0 + .16, 0), P(x1 + .1, y1 + .16, 0), P(x0 + .1, y1 + .16, 0)]))
        top_pts = [P(x0, y0, h), P(x1, y0, h), P(x1, y1, h), P(x0, y1, h)]
        if b["tier"] == "einstants":
            glow.append(poly(top_pts))
        # The side the camera can see: west faces right of the camera, east faces left of it
        if cam.pos[0] < x0:
            body.append(poly([P(x0, y0, 0), P(x0, y1, 0), P(x0, y1, h), P(x0, y0, h)], fill=west))
        elif cam.pos[0] > x1:
            body.append(poly([P(x1, y0, 0), P(x1, y1, 0), P(x1, y1, h), P(x1, y0, h)], fill=east))
        body.append(poly([P(x0, y1, 0), P(x1, y1, 0), P(x1, y1, h), P(x0, y1, h)], fill=south))
        if b["tier"] == "planned":
            body.append(poly(top_pts, fill=top, stroke="#2DD4BF", stroke_width="2.2", stroke_linejoin="round"))
        else:
            body.append(poly(top_pts, fill=top))
        # The code lies on the top face: an affine map taken at the face centre, so the
        # letters follow the tile's perspective without shearing towards one corner
        nw, ne, se, sw = top_pts
        mid = lambda p, q: ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        (wx, wy), (ex, ey) = mid(nw, sw), mid(ne, se)
        (nx, ny), (sx, sy) = mid(nw, ne), mid(sw, se)
        m = (f"matrix({(ex - wx) / TILE:.3f} {(ey - wy) / TILE:.3f} {(sx - nx) / TILE:.3f} {(sy - ny) / TILE:.3f} "
             f"{(wx + ex) / 2:.1f} {(ny + sy) / 2:.1f})")
        size = 0.25 if len(b["code"]) > 2 else 0.3
        body.append(f'<text transform="{m}" x="0" y="0" font-size="{size}" '
                    f'fill="{ink}" fill-opacity="{ink_op}" text-anchor="middle" dominant-baseline="central">{b["code"]}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <radialGradient id="studio" cx="{v["light"][0]}" cy="{v["light"][1]}" r="62%">
      <stop offset="0" stop-color="#4A4547"/><stop offset=".72" stop-color="{v["ground"]}"/>
    </radialGradient>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="{tile_px * .4:.1f}"/></filter>
    <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="{tile_px * .55:.1f}"/></filter>
    <filter id="haze" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="{tile_px * 1.6:.1f}"/></filter>
  </defs>
  <rect width="{W}" height="{H}" fill="{v["ground"]}"/>
  <rect width="{W}" height="{H}" fill="url(#studio)"/>
  <g filter="url(#soft)" fill="#121011" opacity=".42">{''.join(shadow)}</g>
  <g filter="url(#haze)" fill="#2DD4BF" opacity=".16">{''.join(glow)}</g>
  <g filter="url(#glow)" fill="#2DD4BF" opacity=".32">{''.join(glow)}</g>
  <g font-family="'Geist Mono', ui-monospace, monospace" font-weight="600" letter-spacing=".02">{''.join(body)}</g>
</svg>"""


def render(page, svg, v, tmp):
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@600&display=block">
<style>html,body{{margin:0;background:{v["ground"]}}}svg{{display:block}}</style></head><body>{svg}</body></html>"""
    page_path = os.path.join(tmp, f"board{v['suffix']}.html")
    open(page_path, "w", encoding="utf-8").write(html)
    master = os.path.join(tmp, f"master{v['suffix']}.png")
    page.set_viewport_size({"width": v["W"], "height": v["H"]})
    page.goto("file://" + page_path, wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    page.screenshot(path=master)
    return Image.open(master).convert("RGB")


def main():
    atlas = json.load(open(ATLAS, encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        for v in VARIANTS:
            img = render(page, build_svg(atlas["register"]["tiles"], v), v, tmp)
            name = NAME + v["suffix"]
            for width in v["widths"]:
                im = img.resize((width, round(width * v["H"] / v["W"])), Image.LANCZOS)
                im.save(os.path.join(OUT, f"{name}-{width}.webp"), "WEBP", quality=88, method=6)
            jpg = img.resize((v["jpg"], round(v["jpg"] * v["H"] / v["W"])), Image.LANCZOS)
            jpg.save(os.path.join(OUT, f"{name}-{v['jpg']}.jpg"), "JPEG", quality=88, optimize=True, progressive=True)
        browser.close()
    for f in sorted(os.listdir(OUT)):
        print(f"{f:40s} {os.path.getsize(os.path.join(OUT, f)) / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
