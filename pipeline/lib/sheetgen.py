"""Rect-based A3 drawing sheets (PIL rasteriser — no cairosvg in this build).

Every sheet is drawn from `lib/rectwalls.py`, the same module `lib/bbuild.py`
uses for the 3D model, so a plan can never disagree with its render.

    python3 -m lib.sheetgen <scheme_module> <outdir> [--dpi 200]

Writes: 00_index, 01_site, 02_plans_a (levels 1-2), 03_plans_b (level 3 + roof),
        04_section, 05_schedule  — all A3 landscape PNG.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from .rectwalls import level_walls, net_area, schedule, label as nice

try:
    from . import plangen as P
    KIND = P.KIND
    PLOT_W, PLOT_D = P.PLOT_W, P.PLOT_D
    HX0, HX1, HY0, HY1 = P.HX0, P.HX1, P.HY0, P.HY1
    LANE_X = P.LANE_X
except Exception:                                    # pragma: no cover
    KIND = {'hab': ('#f6f2ea', 'none', 'HABITABLE'),
            'serv': ('#e7e9e6', 'tile', 'SERVICE / WET'),
            'circ': ('#efece4', 'none', 'CIRCULATION'),
            'out': ('#dfe4d6', 'deck', 'OUTDOOR'),
            'water': ('#cfe0e2', 'none', 'WATER'),
            'store': ('#ece5d6', 'none', 'STORAGE'),
            'spec': ('#e9dfd6', 'none', 'SPECIAL'),
            'plant': ('#dde3cf', 'leaf', 'PLANT / VOID')}
    PLOT_W, PLOT_D, HX0, HX1, HY0, HY1 = 13.5, 65.0, 0.30, 11.30, 0.0, 19.80
    LANE_X = (11.30, 13.5)

A3W, A3H = 420.0, 297.0
MARG = 9.0
INK = (36, 31, 26)
GREY = (110, 103, 92)
LGREY = (152, 145, 133)
POCHE = (54, 48, 43)
POCHE_L = (104, 97, 88)
PAPER = (253, 252, 249)
GLASS = (110, 152, 162)
RED = (178, 69, 47)
BLUE = (52, 92, 118)
GREEN = (47, 107, 52)
HATCHC = (170, 163, 150)

_FONTS = {}


def font(size_mm, bold=False, dpi=200, italic=False):
    key = (round(size_mm, 2), bold, italic, dpi)
    if key not in _FONTS:
        base = '/usr/share/fonts/truetype/dejavu/DejaVuSans'
        suf = ('-BoldOblique.ttf' if bold and italic else
               '-Bold.ttf' if bold else
               '-Oblique.ttf' if italic else '.ttf')
        path = base + suf
        if not os.path.exists(path):
            path = '/usr/share/fonts/truetype/liberation/LiberationSans-%s.ttf' % (
                'Bold' if bold else 'Regular')
        _FONTS[key] = ImageFont.truetype(path, max(6, int(round(size_mm * dpi / 25.4))))
    return _FONTS[key]


# ------------------------------------------------------------------ primitives --

class Sheet:
    def __init__(self, dpi=200, title='', sheet_no=''):
        self.dpi = dpi
        self.k = dpi / 25.4
        self.im = Image.new('RGB', (int(A3W * self.k), int(A3H * self.k)), PAPER)
        self.d = ImageDraw.Draw(self.im)
        self.title = title
        self.sheet_no = sheet_no

    def px(self, mm):
        return mm * self.k

    def save(self, path):
        self.im.save(path)
        return path

    def line(self, p0, p1, w=0.18, c=INK, dash=None):
        wpx = max(1, int(round(w * self.k / 2)))
        if dash is None:
            self.d.line([self.px(p0[0]), self.px(p0[1]), self.px(p1[0]), self.px(p1[1])],
                        fill=c, width=wpx)
            return
        (x0, y0), (x1, y1) = p0, p1
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-9:
            return
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        on, off = dash
        t = 0.0
        while t < L:
            t2 = min(L, t + on)
            self.d.line([self.px(x0 + ux * t), self.px(y0 + uy * t),
                         self.px(x0 + ux * t2), self.px(y0 + uy * t2)], fill=c, width=wpx)
            t = t2 + off

    def rect(self, x, y, w, h, fill=None, stroke=INK, sw=0.18, dash=None):
        box = [self.px(x), self.px(y), self.px(x + w), self.px(y + h)]
        if fill is not None:
            self.d.rectangle(box, fill=fill)
        if stroke is not None:
            wpx = max(1, int(round(sw * self.k / 2)))
            if dash is None:
                self.d.rectangle(box, outline=stroke, width=wpx)
            else:
                for a, b in ((((box[0], box[1]), (box[2], box[1]))),
                             (((box[2], box[1]), (box[2], box[3]))),
                             (((box[2], box[3]), (box[0], box[3]))),
                             (((box[0], box[3]), (box[0], box[1])))):
                    self.line(a, b, sw, stroke, dash)

    def poly(self, pts, fill=None, stroke=INK, sw=0.18, dash=None):
        p = [(self.px(a), self.px(b)) for a, b in pts]
        if fill is not None:
            self.d.polygon(p, fill=fill)
        if stroke is not None:
            wpx = max(1, int(round(sw * self.k / 2)))
            if dash is None:
                self.d.line(p + [p[0]], fill=stroke, width=wpx, joint='curve')
            else:
                for i in range(len(p)):
                    self.line(p[i], p[(i + 1) % len(p)], sw, stroke, dash)

    def circ(self, cx, cy, r, fill=None, stroke=INK, sw=0.18):
        self.d.ellipse([self.px(cx - r), self.px(cy - r), self.px(cx + r), self.px(cy + r)],
                       fill=fill, outline=stroke, width=max(1, int(round(sw * self.k / 2))))

    def tw(self, s, size=2.6, bold=False, italic=False):
        bb = self.d.textbbox((0, 0), str(s), font=font(size, bold, self.dpi, italic))
        return (bb[2] - bb[0]) / self.k

    def text(self, x, y, s, size=2.6, anchor='ls', bold=False, c=INK, ls=0.0,
             italic=False, rot=0):
        s = str(s)
        if ls:
            s = ' '.join(s)
        f = font(size, bold, self.dpi, italic)
        if rot:
            w = int(self.tw(s, size, bold, italic) * self.k) + 12
            h = int(size * self.k * 1.9) + 10
            lay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(lay).text((6, 4), s, font=f, fill=tuple(c) + (255,))
            lay = lay.rotate(rot, expand=True)
            bb = lay.getbbox()
            dx = {'la': 0, 'ls': 0, 'ca': lay.width / 2, 'ma': (lay.width - bb[2]) / 2,
                  'ms': (lay.width - bb[2]) / 2, 'ra': lay.width - bb[2],
                  'rs': lay.width - bb[2], 'mm': (lay.width - bb[2]) / 2,
                  'lm': 0, 'lb': 0}.get(anchor, 0)
            dy = {'la': 0, 'ls': 0, 'ca': lay.height / 2, 'ma': 0, 'ms': 0,
                  'ra': 0, 'rs': 0, 'mm': (lay.height - bb[3]) / 2, 'lm': 0,
                  'lb': lay.height - bb[3]}.get(anchor, 0)
            self.im.paste(lay, (int(self.px(x) - dx), int(self.px(y) - dy)), lay)
            return
        self.d.text((self.px(x), self.px(y)), s, font=f, fill=tuple(c), anchor=anchor)

    def hatch(self, x, y, w, h, kind='tile', spacing=2.2, c=HATCHC, sw=0.14):
        """45 degree hatch clipped exactly to the rect (mm)."""
        if w <= 0.05 or h <= 0.05:
            return
        x1, y1 = x + w, y + h
        if kind == 'leaf':
            yy = y + spacing * 0.5
            while yy < y1:
                xx = x + spacing * 0.5
                while xx < x1:
                    self.d.ellipse([self.px(xx - 0.32), self.px(yy - 0.32),
                                    self.px(xx + 0.32), self.px(yy + 0.32)], fill=c)
                    xx += spacing
                yy += spacing
            return
        if kind == 'cross':
            self.hatch(x, y, w, h, 'tile', spacing, c, sw)
            lay = Image.new('RGBA', (self.im.width, self.im.height), (0, 0, 0, 0))
            dd = ImageDraw.Draw(lay)
            dd.line([self.px(x), self.px(y), self.px(x1), self.px(y1)],
                    fill=tuple(c) + (255,), width=max(1, int(sw * self.k / 2)))
            dd.line([self.px(x), self.px(y1), self.px(x1), self.px(y)],
                    fill=tuple(c) + (255,), width=max(1, int(sw * self.k / 2)))
            self.im.paste(Image.composite(lay, Image.new('RGBA', lay.size, (0, 0, 0, 0)), lay),
                          (0, 0),
                          Image.new('L', lay.size, 0).point(lambda v: 255) if False else
                          lay.split()[3])
            return
        s = spacing
        csum = (x + y) - (x1 + y) - s
        while csum < x1 + y1:
            a = max(x, csum - y1)
            b = min(x1, csum - y)
            if b - a > 0.12:
                self.line((a, csum - a), (b, csum - b), sw, c)
            csum += s

    # -- furniture ------------------------------------------------------------
    def frame(self):
        self.rect(1.0, 1.0, A3W - 2, A3H - 2, None, INK, 0.7)
        self.line((MARG, MARG + 6.4), (A3W - MARG, MARG + 6.4), 0.35, INK)
        self.text(MARG, MARG + 4.0, 'FAMILY HOUSE  ·  CONCEPT STUDY  ·  NOT FOR CONSTRUCTION', 2.9,
                  'ls', True, ls=0.7)
        self.text(A3W - MARG, MARG + 4.0, self.title, 2.9, 'rs', True, ls=0.3)
        self.rect(1.0, 1.0, A3W - 2, A3H - 2, None, None)

    def title_block(self, S, scale_txt, sheet_name):
        bw, bh = 132.0, 28.0
        x0, y0 = A3W - MARG - bw, A3H - MARG - bh
        self.rect(x0, y0, bw, bh, (250, 248, 243), INK, 0.6)
        self.line((x0, y0 + 8.2), (x0 + bw, y0 + 8.2), 0.35, INK)
        self.line((x0, y0 + 16.4), (x0 + bw, y0 + 16.4), 0.25, INK)
        self.text(x0 + 2.4, y0 + 2.4, S['title'], 4.3, 'ls', True)
        self.text(x0 + 2.4, y0 + 11.6, S['tagline'], 2.15, 'ls', c=GREY)
        self.text(x0 + 2.4, y0 + 19.6, 'SCALE', 1.9, 'ls', c=GREY)
        self.text(x0 + 2.4, y0 + 23.0, scale_txt, 2.6, 'ls', True)
        self.text(x0 + 46, y0 + 19.6, 'SHEET', 1.9, 'ls', c=GREY)
        self.text(x0 + 46, y0 + 23.0, self.sheet_no, 2.6, 'ls', True)
        self.text(x0 + 46, y0 + 26.4, sheet_name, 2.0, 'ls', c=GREY)
        self.text(x0 + 100, y0 + 19.6, 'STATUS', 1.9, 'ls', c=GREY)
        self.text(x0 + 100, y0 + 23.0, 'FOR REVIEW', 2.6, 'ls', True, c=RED)
        self.text(x0 + 100, y0 + 26.4, 'not for construction', 2.0, 'ls', c=GREY, italic=True)

    def north(self, x, y, r=6.0):
        self.circ(x, y, r, None, INK, 0.3)
        self.poly([(x, y - r * 0.92), (x - r * 0.30, y + r * 0.42), (x, y + r * 0.14)], INK)
        self.poly([(x, y - r * 0.92), (x + r * 0.30, y + r * 0.42), (x, y + r * 0.14)],
                  None, INK, 0.2)
        self.text(x, y + r * 0.55, 'N', 3.1, 'ma', True)

    def scalebar(self, x, y, mm, label_m=10):
        self.rect(x, y, mm, 1.4, (243, 240, 233), INK, 0.25)
        n = max(1, int(mm // label_m))
        for i in range(n):
            self.rect(x + i * label_m, y, label_m, 1.4,
                      INK if i % 2 == 0 else (243, 240, 233), INK, 0.18)
        for i in range(n + 1):
            self.text(x + i * label_m, y - 1.1, str(i * label_m), 1.85, 'mb', c=GREY)
        self.text(x + mm + 2.0, y + 1.2, 'metres  (assumed — no survey)', 1.85, 'ls', c=GREY)

    def key(self, x, y, items, title='KEY', sw=4.4, sh=2.6, gap=1.4, size=2.1):
        self.text(x, y, title, 2.3, 'ls', True)
        yy = y + 3.4
        for fill, hatch, lab in items:
            self.rect(x, yy, sw, sh, fill, INK, 0.2)
            if hatch != 'none':
                self.hatch(x, yy, sw, sh, hatch, 1.15, (160, 153, 140), 0.1)
            self.text(x + sw + 1.5, yy + 1.3, lab, size, 'lm')
            yy += sh + gap
        return yy

    def notes(self, x, y, lines, title='NOTES', size=2.0, w=None, lh=2.85, c=GREY):
        self.text(x, y, title, 2.3, 'ls', True)
        yy = y + 3.6
        for ln in lines:
            words, cur, out = str(ln).split(' '), '', []
            for wd in words:
                t = (cur + ' ' + wd).strip()
                if w and self.tw(t, size) > w:
                    out.append(cur)
                    cur = wd
                else:
                    cur = t
            out.append(cur)
            for seg in out:
                self.text(x, yy, seg, size, 'ls', c=c)
                yy += lh
            yy += 0.4
        return yy

    def table(self, x, y, w, cols, rows, title='', size=2.05, rh=4.2, head=1):
        """cols: [(label, width_mm, align)]; rows: [[str,...]]"""
        if title:
            self.text(x, y, title, 2.6, 'ls', True)
            y += 5.0
        xs, cx = [], x
        for _, cw, _a in cols:
            xs.append((cx, cw))
            cx += cw
        self.line((x, y - 1.0), (x + w, y - 1.0), 0.3, INK)
        for (cx0, cw), (lab, _, al) in zip(xs, cols):
            self.text({'l': cx0, 'r': cx0 + cw, 'c': cx0 + cw / 2}[al], y + 1.2, lab,
                      size * 0.95, {'l': 'ls', 'r': 'rs', 'c': 'ms'}[al], True, GREY)
        self.line((x, y + 2.8), (x + w, y + 2.8), 0.2, INK)
        yy = y + 3.4
        for i, row in enumerate(rows):
            for (cx0, cw), val, (_, _, al) in zip(xs, row, cols):
                bold = str(val).startswith('**')
                t = str(val).replace('**', '')
                self.text({'l': cx0, 'r': cx0 + cw, 'c': cx0 + cw / 2}[al], yy, t,
                          size, {'l': 'ls', 'r': 'rs', 'c': 'ms'}[al], bold)
            yy += rh
            if head and i == head - 1:
                self.line((x, yy - 1.2), (x + w, yy - 1.2), 0.2, INK)
        self.line((x, yy - 1.2), (x + w, yy - 1.2), 0.3, INK)
        return yy


class View:
    """Maps model metres into a mm box on the sheet."""

    def __init__(self, sh, box, bb, scale=None):
        self.s = sh
        self.x0, self.y0, self.w, self.h = box
        fx0, fy0, fx1, fy1 = bb
        if scale:
            self.s_mm = scale
        else:
            self.s_mm = min(self.w / max(1e-6, fx1 - fx0), self.h / max(1e-6, fy1 - fy0))
        self.ox = self.x0 + (self.w - (fx1 - fx0) * self.s_mm) / 2
        self.oy = self.y0 + (self.h - (fy1 - fy0) * self.s_mm) / 2
        self.bb = bb

    def X(self, x):
        return self.ox + (x - self.bb[0]) * self.s_mm

    def Y(self, y):
        return self.oy + (self.bb[3] - y) * self.s_mm

    def m(self, v):
        return v * self.s_mm

    def rect(self, r, fill=None, stroke=INK, sw=0.18, dash=None):
        self.s.rect(self.X(r[0]), self.Y(r[3]), self.m(r[2] - r[0]), self.m(r[3] - r[1]),
                    fill, stroke, sw, dash)

    def hatch(self, r, kind, spacing_mm=2.2):
        self.s.hatch(self.X(r[0]), self.Y(r[3]), self.m(r[2] - r[0]), self.m(r[3] - r[1]),
                     kind, spacing_mm)

    def line(self, a, b, w=0.18, c=INK, dash=None):
        self.s.line((self.X(a[0]), self.Y(a[1])), (self.X(b[0]), self.Y(b[1])), w, c, dash)

    def poly(self, pts, fill=None, stroke=INK, sw=0.18, dash=None):
        self.s.poly([(self.X(a), self.Y(b)) for a, b in pts], fill, stroke, sw, dash)

    def arcpts(self, cx, cy, r, a0, a1, steps=16):
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
               for i in range(steps + 1)]
        self.s.d.line([(self.s.px(self.X(a)), self.s.px(self.Y(b))) for a, b in pts],
                      fill=GREY, width=1)

    def circ(self, a, b, r, fill=None, stroke=INK, sw=0.18):
        self.s.circ(self.X(a), self.Y(b), r * self.s_mm, fill, stroke, sw)

    def text(self, a, b, s, size=2.6, anchor='mm', bold=False, c=INK, **kw):
        self.s.text(self.X(a), self.Y(b), s, size, anchor, bold, c, **kw)


KEY_ITEMS = [(KIND[k][0], KIND[k][1], KIND[k][2])
             for k in ('hab', 'serv', 'circ', 'store', 'spec', 'out', 'plant')]


def _door_swing(v, w, o0, o1):
    """Hinged leaf + quarter-circle swing, radius = leaf width."""
    wd = o1 - o0
    if wd < 0.35:
        return
    mid = (o0 + o1) / 2
    hinge, away = (o0, +1) if (mid - o0) >= (o1 - mid) else (o1, -1)
    if w['axis'] == 'x':                      # wall runs along X at y = coord
        c = w['coord']
        v.arcpts(hinge, c, wd, 0 if away > 0 else 180,
                 90 if away > 0 else 270)
        v.line((hinge, c), (hinge, c + away * wd), 0.3, INK)
    else:                                     # wall runs along Y at x = coord
        c = w['coord']
        v.arcpts(c, hinge, wd, 90 if away > 0 else 270,
                 180 if away > 0 else 0)
        v.line((c, hinge), (c + away * wd, hinge), 0.3, INK)


def _sldoor(v, w, o0, o1):
    """Sliding leaf shown open, with track."""
    t = w['thick']
    c = w['coord']
    mid = (o0 + o1) / 2
    if w['axis'] == 'x':
        v.line((mid, c - t / 2), (mid, c + t / 2), 0.35, INK)
        v.line((o0 - 0.2, c - t / 2 - 0.45), (mid, c - t / 2 - 0.45), 0.35, INK)
        v.line((mid, c + t / 2 + 0.45), (o1 + 0.2, c + t / 2 + 0.45), 0.35, INK)
    else:
        v.line((c - t / 2, mid), (c + t / 2, mid), 0.35, INK)
        v.line((c - t / 2 - 0.45, o0 - 0.2), (c - t / 2 - 0.45, mid), 0.35, INK)
        v.line((c + t / 2 + 0.45, mid), (c + t / 2 + 0.45, o1 + 0.2), 0.35, INK)


def plan(v, S, lv, sh, sec_at=None, compact=False):
    """Draw one level plan into view v."""
    walls = level_walls(S, lv)
    for nm, x0, y0, x1, y1, k in lv['rooms']:
        fill, hatch, _ = KIND.get(k, KIND['hab'])
        v.rect((x0, y0, x1, y1), fill)
        if hatch != 'none':
            v.hatch((x0, y0, x1, y1), hatch, 2.4 if v.s_mm > 6 else 1.4)

    for w in walls:
        c, a, b, t = w['coord'], w['t0'], w['t1'], w['thick']
        r = (a, c - t / 2, b, c + t / 2) if w['axis'] == 'x' else (c - t / 2, a, c + t / 2, b)
        v.rect(r, POCHE if w.get('ext') else POCHE_L)
    for w in walls:
        c, t = w['coord'], w['thick']
        for (o0, o1, sill, head, kind) in w['openings']:
            r = ((o0, c - t / 2, o1, c + t / 2) if w['axis'] == 'x'
                 else (c - t / 2, o0, c + t / 2, o1))
            v.rect(r, (247, 246, 242))
            if kind == 'window':
                for f in (-0.30, 0.30):
                    if w['axis'] == 'x':
                        v.line((o0, c + f * t), (o1, c + f * t), 0.28, GLASS)
                    else:
                        v.line((c + f * t, o0), (c + f * t, o1), 0.28, GLASS)
            elif kind == 'door':
                _door_swing(v, w, o0, o1)
            elif kind == 'sldoor':
                _sldoor(v, w, o0, o1)
            elif kind == 'garage':
                if w['axis'] == 'x':
                    v.line((o0, c), (o1, c), 0.45, INK, (2.4, 1.2))
                else:
                    v.line((c, o0), (c, o1), 0.45, INK, (2.4, 1.2))

    wx = sorted({round(w['coord'], 3) for w in walls if w['axis'] == 'y'})
    wy = sorted({round(w['coord'], 3) for w in walls if w['axis'] == 'x'})

    def free_cell(x0, y0, x1, y1):
        """Largest wall-free sub-rectangle of a room, so a label never lands on a wall."""
        cxs = [x0] + [c for c in wx if x0 + 1e-6 < c < x1 - 1e-6] + [x1]
        cys = [y0] + [c for c in wy if y0 + 1e-6 < c < y1 - 1e-6] + [y1]
        best = (x0, y0, x1, y1)
        ba = 0.0
        for i in range(len(cxs) - 1):
            for j in range(len(cys) - 1):
                a, b, c, d = cxs[i], cys[j], cxs[i + 1], cys[j + 1]
                ar = (c - a) * (d - b)
                if ar > ba:
                    ba, best = ar, (a, b, c, d)
        return best

    for nm, kind, a2 in sorted(schedule(S, lv), key=lambda t: -t[2]):
        rs = [r for r in lv['rooms'] if r[0] == nm]
        if not rs:
            continue
        x0 = min(r[1] for r in rs); y0 = min(r[2] for r in rs)
        x1 = max(r[3] for r in rs); y1 = max(r[4] for r in rs)
        if v.m(x1 - x0) < 9 or v.m(y1 - y0) < 5.5:
            continue
        cx0, cy0, cx1, cy1 = free_cell(x0, y0, x1, y1)
        bw, bh = v.m(cx1 - cx0), v.m(cy1 - cy0)
        if bw < 8 or bh < 4.5:
            continue
        nm2 = nice(nm).upper()
        fs = 2.45
        words = nm2.split(' ')
        lines = [nm2]
        if sh.tw(nm2, fs, True) > bw - 1.2 and len(words) > 1:
            best, bs = None, 1e9
            for k in range(1, len(words)):
                t1, t2 = ' '.join(words[:k]), ' '.join(words[k:])
                wmax = max(sh.tw(t1, fs, True), sh.tw(t2, fs, True))
                if wmax < bs:
                    bs, best = wmax, [t1, t2]
            lines = best or [nm2]
        while lines and max(sh.tw(t, fs, True) for t in lines) > bw - 0.8:
            fs -= 0.1
            if fs < 1.35:
                lines = [nm2[:14]]
                break
        if len(lines) == 1 and sh.tw(lines[0], fs, True) > bw - 0.8:
            continue
        cx, cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        two = len(lines) == 2
        area_ok = bh > (12.0 if two else 9.5) and fs > 1.6
        dy = (fs * 0.78) / v.s_mm
        if two:
            v.text(cx, cy + dy, lines[0], fs, 'mm', True)
            v.text(cx, cy - dy, lines[1], fs, 'mm', True)
        else:
            v.text(cx, cy + ((2.6 / v.s_mm) if area_ok else 0), lines[0], fs, 'mm', True)
        if area_ok:
            v.text(cx, cy - (3.4 / v.s_mm if not two else (fs * 1.55 + 2.0) / v.s_mm),
                   f'{a2:.1f} m²', fs * 0.92, 'mm', False, GREY)

    xs = sorted({HX0, HX1} | {round(q, 3) for r in lv['rooms'] for q in (r[1], r[3])})
    ys = sorted({HY0, HY1} | {round(q, 3) for r in lv['rooms'] for q in (r[2], r[4])})
    top, bot = v.Y(HY1), v.Y(HY0)
    for i, xx in enumerate(xs):
        X = v.X(xx)
        sh.line((X, bot + 1.5), (X, top - 1.5), 0.12, (202, 196, 186), (1.8, 1.6))
        sh.circ(X, top - 4.4, 2.5, PAPER, LGREY, 0.22)
        sh.text(X, top - 4.4, chr(65 + i), 2.1, 'mm', True)
    for j, yy in enumerate(ys):
        Y = v.Y(yy)
        sh.line((v.X(HX0) - 1.5, Y), (v.X(HX1) + 1.5, Y), 0.12, (202, 196, 186), (1.8, 1.6))
        sh.circ(v.X(HX1) + 4.4, Y, 2.5, PAPER, LGREY, 0.22)
        sh.text(v.X(HX1) + 4.4, Y, str(j + 1), 2.1, 'mm', True)

    if sec_at is not None:
        Y = v.Y(sec_at)
        sh.line((v.X(HX0) - 7, Y), (v.X(HX1) + 7, Y), 0.5, RED, (5, 2.5))
        for xx in (v.X(HX0) - 7, v.X(HX1) + 7):
            sh.poly([(xx, Y - 1.6), (xx + 2.8, Y), (xx, Y + 1.6)], RED)
        sh.text(v.X(HX0) + 2.0, Y - 2.4, 'SECTION  A–A', 2.2, 'ls', True, RED)
    return walls


def dims(v, sh):
    """Chain + overall dimensions west and south of the plan, in reserved margin."""
    xs = sorted({HX0, HX1} | {round(q, 3) for _, x0, y0, x1, y1, k in
                             [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in []]})
    return


def draw_plan_sheet(sh, S, panels, sheet_no, title):
    """panels: [('plan', level_index), ..., ('roof', None)]"""
    sh.title = S['title'] + '  ·  ' + title
    sh.sheet_no = sheet_no
    sh.frame()
    n = len(panels)
    pw, gap = 104.0, 16.0
    tot = n * pw + (n - 1) * gap
    x_start = max(MARG + 4, (A3W - 148 - tot) / 2)
    by, bh = 36.0, 196.0
    for j, (kind, arg, _x) in enumerate(panels):
        bx = x_start + j * (pw + gap)
        if kind == 'plan':
            lv = S['levels'][arg]
            v = View(sh, (bx, by, pw, bh), (HX0 - 0.2, HY0 - 0.2, HX1 + 0.2, HY1 + 0.2),
                     scale=min(pw / (HX1 - HX0 + 0.4), bh / (HY1 - HY0 + 0.4)))
            sh.text(bx + pw / 2, by - 8.6, 'enclosed %.1f m²   ·   level %d of %d'
                    % (net_area(S, lv), arg + 1, len(S['levels'])), 2.1, 'ms', c=GREY)
            sh.text(bx + pw / 2, by - 4.4, lv['name'] + '   ·   FFL %+.2f / %+.2f'
                    % (lv['z'], lv['ztop']), 3.0, 'ms', True)
            plan(v, S, lv, sh, sec_at=S.get('section_cut') if j == 0 else None)
            _dim(v, sh, S, lv)
            sh.north(bx + pw - 5.0, by + bh - 7.0, 5.4)
        else:
            rs = S['levels'][0]['rooms']
            fx0, fy0 = min(r[1] for r in rs), min(r[2] for r in rs)
            fx1, fy1 = max(r[3] for r in rs), max(r[4] for r in rs)
            ov = max(r.get('overhang', 1.0) for r in S['massing']['roofs'])
            v = View(sh, (bx, by, pw, bh),
                     (fx0 - ov - 1.5, fy0 - ov - 1.5, fx1 + ov + 1.5, fy1 + ov + 1.5))
            sh.text(bx + pw / 2, by - 8.6, 'eaves %+.2f  ·  ridge %+.2f  ·  overhang %.2f m'
                    % (S['massing']['roofs'][0]['ze'],
                       max(r['zr'] for r in S['massing']['roofs']), ov), 2.1, 'ms', c=GREY)
            sh.text(bx + pw / 2, by - 4.4, 'ROOF PLAN  ·  looking down', 3.0, 'ms', True)
            _roof_plan(v, S)
            sh.north(bx + pw - 5.0, by + bh - 7.0, 5.4)
    kx = x_start + tot + 16
    sh.key(kx, 36, KEY_ITEMS)
    sh.notes(kx, 78, S.get('sheet_notes', []) + NOTES_COMMON, w=A3W - MARG - kx - 2)
    sh.scalebar(x_start, A3H - MARG - 20, 50, 10)
    sh.title_block(S, '1:100 at A3', title.lower())
    return sh


def _dim(v, sh, S, lv):
    xs = sorted({HX0, HX1} | {round(q, 3) for r in lv['rooms'] for q in (r[1], r[3])})
    ys = sorted({HY0, HY1} | {round(q, 3) for r in lv['rooms'] for q in (r[2], r[4])})
    top, bot = v.Y(HY1), v.Y(HY0)
    left, right = v.X(HX0), v.X(HX1)
    dy1, dy2 = bot + 5.0, bot + 11.0
    for i in range(len(xs) - 1):
        a, b = xs[i], xs[i + 1]
        sh.line((v.X(a), dy1 - 1.2), (v.X(a), dy1 + 1.2), 0.18, GREY)
        sh.line((v.X(b), dy1 - 1.2), (v.X(b), dy1 + 1.2), 0.18, GREY)
        sh.line((v.X(a), dy1), (v.X(b), dy1), 0.18, GREY)
        sh.text((v.X(a) + v.X(b)) / 2, dy1 - 1.0, f'{b - a:.2f}'.rstrip('0').rstrip('.'),
                1.85, 'mb', c=GREY)
    sh.line((left, dy2), (right, dy2), 0.3, INK)
    for xx in (left, right):
        sh.line((xx, dy2 - 1.3), (xx, dy2 + 1.3), 0.3, INK)
    sh.text((left + right) / 2, dy2 - 1.2, f'{HX1 - HX0:.2f}'.rstrip('0').rstrip('.'),
            2.1, 'mb', True)
    dx1, dx2 = left - 5.0, left - 11.0
    for j in range(len(ys) - 1):
        a, b = ys[j], ys[j + 1]
        sh.line((dx1 - 1.2, v.Y(a)), (dx1 + 1.2, v.Y(a)), 0.18, GREY)
        sh.line((dx1 - 1.2, v.Y(b)), (dx1 + 1.2, v.Y(b)), 0.18, GREY)
        sh.line((dx1, v.Y(a)), (dx1, v.Y(b)), 0.18, GREY)
        sh.text(dx1 - 1.0, (v.Y(a) + v.Y(b)) / 2,
                f'{b - a:.2f}'.rstrip('0').rstrip('.'), 1.85, 'rm', c=GREY, rot=90)
    sh.line((dx2, top), (dx2, bot), 0.3, INK)
    for yy in (top, bot):
        sh.line((dx2 - 1.3, yy), (dx2 + 1.3, yy), 0.3, INK)
    sh.text(dx2 - 1.2, (top + bot) / 2, f'{HY1 - HY0:.2f}'.rstrip('0').rstrip('.'),
            2.1, 'mb', True, rot=90)


# ----------------------------------------------------------------- site plan --

def _site_layers(v, S, bb):
    """Draw every site layer, clipped to the view box bb=(x0,y0,x1,y1)."""
    st = S['site']

    def on(x, y):
        return bb[0] - 0.5 <= x <= bb[2] + 0.5 and bb[1] - 0.5 <= y <= bb[3] + 0.5

    def clip(r):
        return (max(r[0], bb[0]), max(r[1], bb[1]), min(r[2], bb[2]), min(r[3], bb[3]))

    def cr(r, fill=None, stroke=INK, sw=0.18, dash=None):
        c = clip(r)
        if c[2] - c[0] > 0.05 and c[3] - c[1] > 0.05:
            v.rect(c, fill, stroke, sw, dash)

    ont = st['bands']['ONT']['y1']
    if bb[3] > 65:
        ry = st.get('river', {}).get('bank_y', 67.0)
        cr((bb[0], ry, bb[2], bb[3]), (203, 219, 224), None)
        yy = max(ry + 0.4, bb[1])
        while yy < bb[3]:
            v.line((bb[0], yy), (bb[2], yy), 0.2, (166, 195, 202))
            yy += 1.3
        if bb[3] > ry + 2:
            v.text(6, ry + 2.4, 'RIVER (owner-reported, bank unverified)', 2.3, 'mm', True, (72, 105, 114))
    if bb[1] < 0:
        cr((bb[0], bb[1], bb[2], 0), (214, 211, 202), None)
        v.line((bb[0], min(0, bb[3])), (bb[2], min(0, bb[3])), 0.6, (176, 172, 163), (6, 4))
        if bb[1] < -2.5:
            v.text(6, -4.4, 'VILLAGE ROAD / ACCESS (south)', 2.3, 'mm', True, GREY)
    cr((bb[0], 0, bb[2], min(65, bb[3])), (236, 233, 223), None)
    # DNN band: existing land, landscape only
    cr((0, max(ont, bb[1]), PLOT_W, min(65, bb[3])), (226, 236, 216), GREEN, 0.5)
    # ONT band: the only buildable band
    cr((0, max(0, bb[1]), PLOT_W, min(ont, bb[3])), (242, 239, 228), (52, 92, 150), 0.7)
    for px in (4.5, 9.0):
        v.line((px, max(0, bb[1])), (px, min(65, bb[3])), 0.18, LGREY, (1.5, 1.5))
    if LANE_X[1] - LANE_X[0] > 0.2:
        cr((LANE_X[0], 0, LANE_X[1], min(ont, bb[3])), (227, 223, 208), None)
        if bb[1] < 12 and bb[3] > 8:
            v.text((LANE_X[0] + LANE_X[1]) / 2, 10, '%.1f m\n' % (LANE_X[1] - LANE_X[0]) + S.get('passage_label', 'SERVICE\nPASSAGE'),
                   1.6, 'mm', c=GREY)
    cr((0, ont, PLOT_W, ont), None, RED, 0.55, (3, 2))
    if bb[1] < ont + 4 and bb[3] > ont + 1.5:
        v.text(PLOT_W + 0.5, ont + 1.1, 'ONT / DNN LINE (schematic)', 2.0, 'ls', True, RED)
    if bb[1] < ont + 10 and bb[3] > ont + 8:
        v.text(PLOT_W + 0.6, ont + 9, 'DNN  609 m²\nexisting land — planting only\nNO buildings · pools · decks', 1.9, 'ls', True, (60, 110, 60))
    for nb in st.get('neighbours', []):
        r = (nb['x0'], nb['y0'], nb['x1'], nb['y1'])
        if on((r[0] + r[2]) / 2, (r[1] + r[3]) / 2) or (bb[0] < r[2] and bb[2] > r[0] and bb[1] < r[3]):
            cr(r, (214, 210, 202), GREY, 0.4, (1.6, 1.2))
            cy = max(r[1] + 2, min(r[3] - 4, (max(r[1], bb[1]) + min(r[3], bb[3])) / 2))
            v.text((r[0] + r[2]) / 2, cy, 'ASSUMED\n%d-STOREY\nNEIGHBOUR\n(party wall)' % nb.get('storeys', 3), 1.6, 'mm', c=GREY)
    C = S.get('concept', {})
    sd = C.get('fence', {}).get('sides')
    if sd:
        for side, x in (('west', 0.0), ('east', PLOT_W)):
            cur = max(0.0, bb[1])
            brk = sorted(b for b in sd.get('breaks', []) if b[0] == side)
            segs, c0 = [], 0.0
            for _, b0, b1 in brk:
                segs.append((c0, b0)); c0 = b1
            segs.append((c0, sd['y1']))
            for a, b in segs:
                a, b = max(a, bb[1]), min(b, bb[3])
                if b > a:
                    v.line((x, a), (x, b), 0.9, (140, 62, 40))
        if bb[1] < 40 and bb[3] > 36:
            v.text(PLOT_W + 0.6, 40, 'BOUNDARY WALLS\n%.1f m solid brick\nto the water\n(owner instruction:\nconfirm on DNN)' % sd.get('height', 0), 1.7, 'ls', True, (140, 62, 40))
    nw = st.get('existing_nw_building')
    if nw and on((nw['x0'] + nw['x1']) / 2, (nw['y0'] + nw['y1']) / 2):
        cr((nw['x0'], nw['y0'], nw['x1'], nw['y1']), (215, 213, 208), GREY, 0.4, (1.6, 1.2))
        v.text(nw['x1'] + 0.6, (nw['y0'] + nw['y1']) / 2,
               'EXISTING NW BUILDING\nexisting condition only\nposition / ownership: survey', 1.75, 'ls', c=GREY)
    for tx, ty in st.get('trees', []):
        if on(tx, ty):
            v.circ(tx, ty, 1.4, (176, 200, 150), (120, 150, 100), 0.25)

    fp = S['footprint']
    if on((fp[0] + fp[2]) / 2, (fp[1] + fp[3]) / 2):
        for i, lv in enumerate(S['levels']):
            rs = lv['rooms']
            cr((min(r[1] for r in rs), min(r[2] for r in rs),
                max(r[3] for r in rs), max(r[4] for r in rs)),
               None, (60, 54, 48) if i == 0 else LGREY, 0.6 if i == 0 else 0.3,
               None if i == 0 else (1.6, 1.4))
        cr((fp[0] - 1.05, fp[1] - 1.05, fp[2] + 1.05, fp[3] + 1.05), None,
           (150, 70, 50), 0.3, (2.4, 1.6))
        cr(fp, (246, 242, 234), INK, 0.75)
    # anything that oversails the assumed 20 m house zone (cantilevers) must be
    # shown dashed and called out: it is usually a consent question
    for ex in [ex for lv in S['levels'] for ex in lv.get('slab_extra', ())]:
        cr(ex, None, (150, 70, 50), 0.55, (2.8, 1.8))
        v.text((ex[0] + ex[2]) / 2, (ex[1] + ex[3]) / 2,
               'OUTSIDE ONT — NOT PERMITTED', 1.85, 'mm',
               (150, 70, 50))
    gr = S.get('grocery_route')
    if gr:
        pts = [(a, b) for a, b in gr if bb[0] <= a <= bb[2] and bb[1] <= b <= bb[3]]
        if len(pts) > 1:
            v.poly(pts, None, BLUE, 0.6, (3, 1.8))
            px, py = pts[len(pts) // 2]
            v.text(px + 0.5, py - 1.8, "car → butler's pantry → kitchen", 1.9, 'ls', True, BLUE)


def draw_site(sh, S, sheet_no):
    sh.title = S['title'] + '  ·  SITE PLAN'
    sh.sheet_no = sheet_no
    sh.frame()
    sh.text(MARG, 21, 'SITE PLAN  ·  1:200 at A3  ·  shown in two parts so the narrow '
            '13.5 m plot stays readable', 3.1, 'ls', True)
    parts = [('SOUTHERLY PART — ONT band, house, road', (-9, -9, 24, 26), 'A'),
             ('NORTHERLY PART — DNN land, existing NW building, river', (-9, 20, 24, 70), 'B')]
    bw = 116.0
    x0 = MARG + 2
    sc = (bw - 8.0) / max(p[1][2] - p[1][0] for p in parts)
    for j, (cap, bb, tag) in enumerate(parts):
        bh = (bb[3] - bb[1]) * sc + 4.0
        bx = x0 + j * (bw + 12)
        by = 30.0 + (222.0 - bh) / 2
        v = View(sh, (bx, by, bw, bh), bb, scale=sc)
        sh.rect(bx - 1.5, by - 1.5, bw + 3, bh + 3, None, (206, 201, 190), 0.25)
        _site_layers(v, S, bb)
        # dimension of the part
        sh.text(bx + bw / 2, by + bh + 4.2, cap, 2.4, 'ms', True)
        sh.circ(bx + 6.0, by + 6.0, 3.4, PAPER, INK, 0.35)
        sh.text(bx + 6.0, by + 6.0, tag, 2.6, 'mm', True)
        sh.north(bx + bw - 7.0, by + 9.0, 5.2)
        if j == 0:
            v.line((0, -1.4), (PLOT_W, -1.4), 0.25, INK)
            v.text(PLOT_W / 2, -1.4, '13.50', 2.2, 'md', True)
            v.line((-1.8, 0), (-1.8, 20), 0.25, INK)
            v.text(-1.8, 10, '20.00', 2.2, 'mb', True, rot=90)
    sh.scalebar(MARG + 4, A3H - MARG - 12, 50, 10)
    nx = 2 * bw + 12 + x0 + 8
    sh.notes(nx, 24, S.get('site_notes', []) + [
        'Schematic site from owner information only: three side-by-side 4.5 m titles, '
        'about 13.5 × 65 m. No survey. Corners, levels, bank edge and road reserve are unverified.',
        'Structures are shown ONLY inside the ONT road-side band (3 × 88.8 = 266.4 m²). '
        'The 609 m² DNN band is existing land, shown as planting only.',
        'The title sketch shows 6.5 m to the road centreline. It is NOT treated as a verified setback.',
        'Assumed: a 3-storey house on each side built to the property line to about the same 20 m depth. '
        'So the east wall is blank (party wall) and the west wall has high-level windows only.',
        'Side boundary walls run the full length to the water on both property lines (owner instruction). '
        'This is the only structure on DNN land. Confirm it is permitted.',
        'The existing north-west building is an existing condition only. Its position and '
        'ownership are to be surveyed. It is not altered.',
        'Subject to legal merger of the three ONT sections, setbacks, river corridor and permits.',
    ], w=A3W - MARG - nx - 2)
    sh.key(nx, 112, [((242, 239, 228), 'none', 'ONT — buildable band'),
                     ((226, 236, 216), 'none', 'DNN — land / planting only'),
                     ((227, 223, 208), 'none', 'service passage'),
                     ((215, 213, 208), 'none', 'existing NW building'),
                     ((214, 210, 202), 'none', 'assumed 3-storey neighbours'),
                     ((140, 62, 40), 'none', 'boundary walls'),
                     (PAPER, 'none', 'house footprint'),
                     (LGREY, 'none', 'assumed / context')])
    sh.title_block(S, '1:200 at A3', 'site plan')
    return sh


# ------------------------------------------------------------------ roof plan --

def _roof_plan(v, S):
    rs = S['levels'][0]['rooms']
    fx0, fy0 = min(r[1] for r in rs), min(r[2] for r in rs)
    fx1, fy1 = max(r[3] for r in rs), max(r[4] for r in rs)
    ov = max(r.get('overhang', 1.0) for r in S['massing']['roofs'])
    roofs = S['massing']['roofs']
    for lv in S['levels']:
        for w in level_walls(S, lv):
            c, a, b, t = w['coord'], w['t0'], w['t1'], w['thick']
            r = ((a, c - t / 2, b, c + t / 2) if w['axis'] == 'x'
                 else (c - t / 2, a, c + t / 2, b))
            v.rect(r, None, (178, 172, 160), 0.2, (1.6, 1.4))
    for rf in roofs:
        o = rf.get('overhang', 1.0)
        ox0, oy0, ox1, oy1 = rf['x0'] - o, rf['y0'] - o, rf['x1'] + o, rf['y1'] + o
        v.rect((ox0, oy0, ox1, oy1), (240, 235, 226), (150, 118, 92), 0.6)
        v.rect((rf['x0'], rf['y0'], rf['x1'], rf['y1']), (247, 244, 238), (176, 150, 126), 0.35)
        ze, zr = rf['ze'], rf['zr']
        if rf['kind'] == 'flat':
            pt = 0.2
            v.rect((rf['x0'] + pt, rf['y0'] + pt, rf['x1'] - pt, rf['y1'] - pt), None, (150, 118, 92), 0.3)
            xc, yc = (rf['x0'] + rf['x1']) / 2, (rf['y0'] + rf['y1']) / 2
            L = min(1.6, (rf['y1'] - rf['y0']) * 0.3)
            v.line((xc, yc + L / 2), (xc, yc - L / 2), 0.45, RED)
            v.line((xc, yc - L / 2), (xc - 0.25, yc - L / 2 + 0.4), 0.45, RED)
            v.line((xc, yc - L / 2), (xc + 0.25, yc - L / 2 + 0.4), 0.45, RED)
            v.text(xc, rf['y0'] + 0.55, 'FLAT %+.2f  parapet %+.2f' % (ze, zr), 1.7, 'mm', c=GREY)
            continue
        if rf['kind'] == 'gable':
            if rf['axis'] == 'x':
                for xx in (rf['x0'], rf['x1']):
                    v.line((xx, oy0), (xx, oy1), 0.35, (120, 90, 66))
                v.line((rf['x0'], (oy0 + oy1) / 2), (rf['x1'], (oy0 + oy1) / 2), 0.65, RED)
                v.line((ox0, (oy0 + oy1) / 2), (ox1, (oy0 + oy1) / 2), 0.45, RED)
            else:
                for yy in (rf['y0'], rf['y1']):
                    v.line((ox0, yy), (ox1, yy), 0.35, (120, 90, 66))
                v.line(((ox0 + ox1) / 2, rf['y0']), ((ox0 + ox1) / 2, rf['y1']), 0.65, RED)
                v.line(((ox0 + ox1) / 2, oy0), ((ox0 + ox1) / 2, oy1), 0.45, RED)
        else:
            xc, yc = (rf['x0'] + rf['x1']) / 2, (rf['y0'] + rf['y1']) / 2
            hx, hy = (rf['x1'] - rf['x0']) / 2, (rf['y1'] - rf['y0']) / 2
            if _hip_axis(rf) == 'y':
                ry0, ry1 = yc - (hy - hx), yc + (hy - hx)
                v.line((xc, ry0), (xc, ry1), 0.7, RED)          # ridge
                v.line((xc, ry0), (rf['x0'], rf['y0']), 0.45, RED)   # hips
                v.line((xc, ry0), (rf['x1'], rf['y0']), 0.45, RED)
                v.line((xc, ry1), (rf['x0'], rf['y1']), 0.45, RED)
                v.line((xc, ry1), (rf['x1'], rf['y1']), 0.45, RED)
                v.line((xc, ry0), (xc, oy0), 0.4, RED, (3, 2))
                v.line((xc, ry1), (xc, oy1), 0.4, RED, (3, 2))
            else:
                rx0, rx1 = xc - (hx - hy), xc + (hx - hy)
                v.line((rx0, yc), (rx1, yc), 0.7, RED)
                v.line((rx0, yc), (rf['x0'], rf['y0']), 0.45, RED)
                v.line((rx0, yc), (rf['x0'], rf['y1']), 0.45, RED)
                v.line((rx1, yc), (rf['x1'], rf['y0']), 0.45, RED)
                v.line((rx1, yc), (rf['x1'], rf['y1']), 0.45, RED)
                v.line((rx0, yc), (ox0, yc), 0.4, RED, (3, 2))
                v.line((rx1, yc), (ox1, yc), 0.4, RED, (3, 2))
        v.text((ox0 + ox1) / 2, oy0 + 1.1, 'TILE  eaves %+.2f  ridge %+.2f' % (ze, zr),
                1.85, 'mm', c=GREY)
    for item in S['massing'].get('fascia', ()):
        v.rect((item['x0'], item['y0'], item['x1'], item['y1']), None, (150, 60, 40), 0.5,
               (4, 2.5))
    for lv in S['levels']:
        for nm, x0, y0, x1, y1, k in lv['rooms']:
            if k == 'plant':
                v.rect((x0, y0, x1, y1), (222, 232, 214), (120, 150, 100), 0.4, (2.4, 1.6))
                v.text((x0 + x1) / 2, (y0 + y1) / 2, nice(nm).upper(), 1.75, 'mm', (96, 124, 84))
    for nm, x0, y0, x1, y1, k in S['levels'][-1]['rooms']:
        if k == 'out':
            v.rect((x0, y0, x1, y1), None, (120, 110, 96), 0.35, (2.4, 1.6))
            v.text((x0 + x1) / 2, (y0 + y1) / 2, nice(nm).upper(), 1.7, 'mm', GREY)
    return ov, roofs


def draw_roof(sh, S, sheet_no):
    sh.title = S['title'] + '  ·  ROOF PLAN'
    sh.sheet_no = sheet_no
    sh.frame()
    rs = S['levels'][0]['rooms']
    fx0, fy0 = min(r[1] for r in rs), min(r[2] for r in rs)
    fx1, fy1 = max(r[3] for r in rs), max(r[4] for r in rs)
    ov = max(r.get('overhang', 1.0) for r in S['massing']['roofs'])
    v = View(sh, (MARG + 6, 40, 150, 214),
             (fx0 - ov - 1.5, fy0 - ov - 1.5, fx1 + ov + 1.5, fy1 + ov + 1.5))
    ov, roofs = _roof_plan(v, S)
    sh.text(MARG + 6, 30, 'ROOF PLAN  ·  looking down', 3.2, 'ls', True)
    sh.north(MARG + 148, 48, 5.6)
    y = 40 + 214 + 10
    flat = all(r['kind'] == 'flat' for r in roofs)
    lg = [(('membrane flat roofs behind parapets — deck %+.2f, parapet %+.2f' if flat else
            'concrete tile on timber — eaves %+.2f, ridge %+.2f') % (roofs[0]['ze'],
                                                                 max(r['zr'] for r in roofs)),
           (240, 235, 226)),
          ('fall arrow (to box gutter / outlet)' if flat else 'ridge / hip line', RED),
          ('parapet inner line' if flat else 'fascia / eaves edge, 1.05 m overhang', (150, 60, 40)),
          ('rain-garden slot, open to the sky', (120, 150, 100)),
          ('outline of the level below (hidden line)', (178, 172, 160))]
    # roof key and notes live in the right-hand column, clear of the plan view and scale bar
    if flat:
        lg = [t for t in lg if t[1] != (120, 150, 100)]
    kx, y = 276, 80
    sh.text(kx, y, 'ROOF KEY', 2.4, 'ls', True)
    y += 4.6
    for t, c in lg:
        if c == (240, 235, 226):
            sh.rect(kx, y, 5.0, 2.4, c, (150, 118, 92), 0.4)
        else:
            sh.line((kx, y + 1.2), (kx + 5, y + 1.2), 0.5, c)
        sh.text(kx + 6.6, y + 1.2, t, 2.0, 'lm', c=GREY)
        y += 4.6
    sh.scalebar(MARG + 6, A3H - MARG - 8, 50, 10)
    if flat:
        notes = ['Flat roofs: membrane deck %+.2f m, parapets up to %+.2f m above datum, no overhang. '
                 'Falls and outlets to be set at design development.' % (roofs[0]['ze'], max(r['zr'] for r in roofs)),
                 'Roof outlines come from the same rectangles as the plans and the 3D model.',
                 'Rainwater: box gutters behind the parapets to downpipes inside the site; '
                 'nothing may discharge onto the neighbours.']
    else:
        notes = ['Ridge and eaves heights come from the option massing: eaves %+.2f m, ridge '
                 '%+.2f m above datum, %.2f m overhang all round.' % (roofs[0]['ze'], max(r['zr'] for r in roofs), ov),
                 'Hips, ridges and the rain-garden slot are derived from the same rectangles as '
                 'the plans and the 3D model.',
                 'Rainwater from the slot and the roof gardens is the only visible drainage; '
                 'confirm the neighbour-boundary falls before detailing.']
    sh.notes(kx, y + 6, notes, w=A3W - MARG - kx - 2)
    sh.key(276, 34, [(PAPER, 'none', 'roof covering'),
                     (RED, 'none', 'fall arrow' if flat else 'ridge / hip'),
                     ((150, 60, 40), 'none', 'parapet' if flat else 'fascia / eaves'),
                     ((222, 232, 214), 'none', 'open slot below')])
    sh.title_block(S, '1:100 at A3', 'roof plan')
    return sh


# ------------------------------------------------------------------- section --

def _hip_axis(rf):
    """A hip's ridge runs parallel to the roof's longer side."""
    return 'y' if (rf['y1'] - rf['y0']) >= (rf['x1'] - rf['x0']) else 'x'


def _roof_z(rf, x, y):
    """Approximate (height, eaves height) of the roof at (x, y), or None if off."""
    o = rf.get('overhang', 0.0)
    x0, y0, x1, y1 = rf['x0'] - o, rf['y0'] - o, rf['x1'] + o, rf['y1'] + o
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return None
    ze, zr = rf['ze'], rf['zr']
    if rf['kind'] == 'flat':
        return zr, ze
    xc, yc = (rf['x0'] + rf['x1']) / 2, (rf['y0'] + rf['y1']) / 2
    hx, hy = max(1e-6, (rf['x1'] - rf['x0']) / 2), max(1e-6, (rf['y1'] - rf['y0']) / 2)
    if rf['kind'] == 'gable' and rf.get('axis') == 'y':
        return ze + (zr - ze) * max(0.0, 1.0 - abs(x - xc) / hx), ze
    if rf['kind'] == 'gable':
        return ze + (zr - ze) * max(0.0, 1.0 - abs(y - yc) / hy), ze
    # a hip has a flat ridge, not a point: inside the ridge band the height is zr
    if _hip_axis(rf) == 'y' and hy > hx and abs(y - yc) <= hy - hx:
        return (zr if abs(x - xc) <= hx else
                ze + (zr - ze) * (1.0 - (abs(x - xc) - hx) / max(1e-6, hx))), ze
    if _hip_axis(rf) == 'x' and hx > hy and abs(x - xc) <= hx - hy:
        return (zr if abs(y - yc) <= hy else
                ze + (zr - ze) * (1.0 - (abs(y - yc) - hy) / max(1e-6, hy))), ze
    t = max(abs(x - xc) / hx, abs(y - yc) / hy)
    return ze + (zr - ze) * max(0.0, 1.0 - min(1.0, t)), ze


def _group_by_eaves(run, tol=0.02):
    """Split a sampled roof profile wherever the eaves height steps, so a flat
    roof beside a pitched one gets its own build-up instead of one tall slab."""
    out, cur = [], [run[0]]
    for p in run[1:]:
        if abs(p[2] - cur[-1][2]) > tol:
            out.append(cur)
            cur = [p]
        else:
            cur.append(p)
    out.append(cur)
    return [g for g in out if len(g) > 1]


def draw_section(sh, S, cut=8.6, sheet_no=None):
    sh.title = S['title'] + '  ·  SECTION A–A'
    sh.sheet_no = sheet_no or '%s-03' % S['key']
    sh.frame()
    lv = S['levels']
    rf = S['massing']['roofs']
    ze = min(r['ze'] for r in rf)
    zr = max(r['zr'] for r in rf)
    ov = max(r.get('overhang', 1.0) for r in rf)
    bbx = (HX0 - 3.4, 0.0, HX1 + 3.4)
    ztop = max(lv[-1]['ztop'], zr) + 1.4
    box = (MARG + 20, 44, 232, 196)
    s = min(box[2] / (bbx[2] - bbx[0]), box[3] / (ztop + 1.4))
    ox = box[0] + (box[2] - (bbx[2] - bbx[0]) * s) / 2
    oy = box[1] + (box[3] - (ztop + 1.4) * s) / 2

    def X(v):
        return ox + (v - bbx[0]) * s

    def Y(z):
        return oy + (ztop + 1.4 - z) * s

    sh.text(MARG, 24, 'SECTION A–A  ·  looking north at y = %.2f m (assumed cut)' % cut,
            3.2, 'ls', True)
    # ground
    gx0, gx1 = X(bbx[0]) + 2, X(bbx[2]) - 2
    sh.rect(gx0, Y(0.0), gx1 - gx0, 1.2, (206, 202, 190), None)
    sh.line((gx0, Y(0.0)), (gx1, Y(0.0)), 0.7, INK)
    xx = bbx[0] - 1
    while xx < bbx[2] + 1:
        sh.line((X(xx), Y(0.0)), (X(xx - 0.8), Y(-1.2)), 0.15, (168, 162, 150))
        xx += 2.0
    sh.text(X(HX0) - 0.8, Y(-0.25), 'ROAD', 2.1, 'rm', True, GREY)
    sh.text(X(12.4), Y(0.55), '2.2 m LANE', 1.95, 'ms', c=GREY)
    sh.text(X(bbx[0]) + 2, Y(-2.6), 'existing ground level ±0.00 — all levels assumed',
            1.9, 'ls', c=GREY, italic=True)

    # cut walls of every level
    for L in lv:
        for w in level_walls(S, L):
            if w['axis'] != 'y' or not (w['t0'] - 0.4 <= cut <= w['t1'] + 0.4):
                continue
            c, t = w['coord'], w['thick']
            sh.rect(X(c - t / 2), Y(L['ztop']), t * s, (L['ztop'] - L['z']) * s,
                    POCHE if w.get('ext') else POCHE_L, None)
            for (o0, o1, sill, head, kind) in w['openings']:
                if not (w['t0'] <= (o0 + o1) / 2 <= w['t1']):
                    continue
                hh = max(0.0, head - sill)
                sh.rect(X(c - t / 2), Y(L['z'] + head), t * s, hh * s, PAPER, None)
                if kind == 'window':
                    sh.rect(X(c - t / 2), Y(L['z'] + sill), t * s, hh * s, GLASS, None)
                else:
                    sh.rect(X(c - t / 2), Y(L['z'] + head - 0.06), t * s, 0.06 * s, POCHE, None)
        sh.rect(X(bbx[0]), Y(L['ztop']), (bbx[2] - bbx[0]) * s, 0.4, (70, 63, 56), None)
        sh.rect(X(bbx[0]), Y(L['z']), (bbx[2] - bbx[0]) * s, 0.4, (70, 63, 56), None)

    # rooms the cut passes through, drawn after the poche so no wall can
    # cover a label (clipped to the section's drawn width).
    # Two rooms on the same level can share an x-centre — a bedroom over a
    # utility, say — so nudge each label clear of the ones already placed.
    used = []

    def place(cx, z, lab, fs, c, band=None):
        """Draw a label at height z, nudged clear of earlier labels but never
        outside its own storey."""
        # widths come back in mm from the font metrics; the box lives in model
        # metres, so convert before comparing
        w_ = sh.tw(lab, fs, True) / s
        h_ = fs * 1.25 / s
        lo, hi = (band if band else (z - 1.0, z + 1.0))
        y_ = min(max(z, lo + h_ / 2), hi - h_ / 2)
        for i in range(7):
            box = (cx - w_ / 2, y_ - h_ / 2, cx + w_ / 2, y_ + h_ / 2)
            if not any(box[0] < u[2] and u[0] < box[2] and box[1] < u[3]
                       and u[1] < box[3] for u in used):
                break
            step = h_ * 1.2 * (1 if i % 2 == 0 else -1) * ((i // 2) + 1)
            y_ = min(max(y_ + step, lo + h_ / 2), hi - h_ / 2)
        else:
            return
        used.append((cx - w_ / 2, y_ - h_ / 2, cx + w_ / 2, y_ + h_ / 2))
        sh.text(X(cx), Y(y_), lab, fs, 'mm', True, c)

    for L in lv:
        for nm, x0, y0, x1, y1, k in L['rooms']:
            if not (y0 - 0.35 <= cut <= y1 + 0.35) or k in ('out',):
                continue
            x0, x1 = max(x0, bbx[0] + 0.05), min(x1, bbx[2] - 0.05)
            if (x1 - x0) * s < 11:
                continue
            lab = nice(nm).upper()
            fs = 2.1
            while sh.tw(lab, fs, True) > (x1 - x0) * s - 2.0 and fs > 1.25:
                fs -= 0.1
            place((x0 + x1) / 2, L['z'] + (L['ztop'] - L['z']) * 0.55, lab, fs, GREY,
                  (L['z'] + 0.55, L['ztop'] - 0.45))
            if k in ('plant', 'water'):
                place((x0 + x1) / 2, L['z'] + (L['ztop'] - L['z']) * 0.30,
                      'open to sky', 1.7, (110, 134, 96),
                      (L['z'] + 0.45, L['ztop'] - 0.40))

    # roof: sampled height along x at the cut
    xs = [bbx[0] + (bbx[2] - bbx[0]) * i / 192.0 for i in range(193)]
    prof = []
    for x in xs:
        hits = [h for h in (_roof_z(r, x, cut) for r in rf) if h is not None]
        prof.append((x, max(hits)[0], max(hits)[1]) if hits else (x, None, None))
    runs, cur = [], []
    for x, z, e in prof:
        if z is None:
            if len(cur) > 1:
                runs.append(cur)
            cur = []
        else:
            cur.append((x, z, e))
    if len(cur) > 1:
        runs.append(cur)
    for run in runs:
        sh.poly([(X(x), Y(z)) for x, z, _e in run], None, (120, 90, 66), 0.6)
        # fill the build-up between the roof line and that roof's own eaves
        for grp in _group_by_eaves(run):
            gtop = [(X(x), Y(z)) for x, z, _e in grp]
            gbot = [(X(x), Y(grp[0][2])) for x, _z, _e in grp][::-1]
            sh.poly(gtop + gbot, (246, 240, 232), None, 0)
        pk = max(run, key=lambda t: t[1])
        sh.line((X(pk[0]), Y(pk[2])), (X(pk[0]), Y(pk[1])), 0.2, LGREY, (2, 1.5))
        allflat = all(r['kind'] == 'flat' for r in rf)
        sh.text(X(pk[0]), Y(pk[1]) - 0.8, ('PARAPET %+.2f' if allflat else 'RIDGE %+.2f') % pk[1], 2.0, 'mb', True, GREY)
        for x, z, e in (run[0], run[-1]):
            sh.text(X(x) + (0.6 if x < HX0 else -0.6), Y(e), ('ROOF %+.2f' if allflat else 'EAVES %+.2f') % e, 1.95,
                    'ls' if x < HX0 else 'rs', True, GREY)
    ze_lo = min([e for run in runs for _x, _z, e in run] + [ze])
    sh.line((X(bbx[0]), Y(ze_lo)), (X(bbx[2]), Y(ze_lo)), 0.2, LGREY, (2, 1.5))
    sh.line((X(HX0), Y(0)), (X(HX0), Y(ze_lo)), 0.55, INK)
    sh.line((X(HX1), Y(0)), (X(HX1), Y(ze_lo)), 0.55, INK)

    # level dimension chains, left and right
    for i, L in enumerate(lv):
        sh.line((X(HX0) - 2, Y(L['z'])), (X(bbx[0]), Y(L['z'])), 0.2, GREY)
        sh.text(X(bbx[0]) + 0.6, Y(L['z']), '%+.2f' % L['z'], 1.95, 'lm', True, GREY)
        sh.text(X(bbx[0]) - 1.6, Y((L['z'] + L['ztop']) / 2), L['name'].title(), 2.1, 'rm',
                True, GREY, rot=90)
        if i + 1 < len(lv):
            gap = lv[i + 1]['z'] - L['ztop']
            sh.text(X(bbx[0]) - 1.6, Y((L['ztop'] + lv[i + 1]['z']) / 2), '%.2f' % gap,
                    1.85, 'rm', False, GREY, rot=90)
        sh.line((X(HX1) + 3, Y(L['z'])), (X(HX1) + 9, Y(L['z'])), 0.15, GREY)
        sh.line((X(HX1) + 3, Y(L['ztop'])), (X(HX1) + 9, Y(L['ztop'])), 0.15, GREY)
        sh.line((X(HX1) + 9, Y(L['z'])), (X(HX1) + 9, Y(L['ztop'])), 0.2, INK)
        sh.text(X(HX1) + 9.6, Y((L['z'] + L['ztop']) / 2), '%.2f' % (L['ztop'] - L['z']),
                2.0, 'lm', True)
    xo_l, xo_r = X(bbx[0]) - 7.0, X(bbx[2]) + 1.0
    sh.line((xo_l, Y(0)), (xo_l, Y(lv[-1]['ztop'])), 0.3, INK)
    for z in (0.0, lv[-1]['ztop']):
        sh.line((xo_l - 1.3, Y(z)), (xo_l + 1.3, Y(z)), 0.3, INK)
    sh.text(xo_l - 1.1, Y(lv[-1]['ztop'] / 2), '%.2f to top FFL' % lv[-1]['ztop'],
            2.1, 'mb', True, rot=90)
    sh.line((xo_r, Y(0)), (xo_r, Y(ze_lo)), 0.3, INK)
    for z in (0.0, ze_lo):
        sh.line((xo_r - 1.3, Y(z)), (xo_r + 1.3, Y(z)), 0.3, INK)
    sh.text(xo_r + 1.1, Y(ze_lo / 2), '%.2f eaves' % ze_lo, 2.1, 'mb', True, rot=90)

    sh.north(X(HX1) + 6, Y(zr) + 4.5, 5.0)
    sh.scalebar(X(bbx[0]) + 2, Y(-1.2) + 7.4, 50, 10)
    sh.key(276, 34, [(POCHE, 'none', 'cut external wall, 0.30'),
                     (POCHE_L, 'none', 'cut internal wall, 0.15'),
                     (GLASS, 'none', 'glazing in the cut'),
                     ((246, 240, 232), 'none', 'roof build-up in section')])
    sh.notes(276, 68, [
        'Datum 0.00 = existing road and ground level. Finished ground floor %+.2f m, '
        'first %+.2f m%s, eaves %+.2f m, ridge %+.2f m.'
        % (lv[0]['z'], lv[1]['z'] if len(lv) > 1 else 0,
           (', second %+.2f m' % lv[2]['z']) if len(lv) > 2 else '', ze, zr),
        'Slabs, walls and levels come from the same rectangles as the plans, so the '
        'section and the plans can never disagree.',
        'The 2.2 m rain-garden slot is open to the sky on every level: draw it as a '
        'full-height void when the structure is detailed.',
        'The cut is at y = %.2f m. Move it on the plans to suit a later survey.' % cut,
    ], w=126)
    sh.title_block(S, '1:100 at A3', 'section A–A')
    return sh


# ------------------------------------------------------------------ schedule --

def draw_schedule(sh, S, sheet_no):
    sh.title = S['title'] + '  ·  AREA SCHEDULE'
    sh.sheet_no = sheet_no
    sh.frame()
    sh.text(MARG, 24, 'AREA SCHEDULE  ·  net internal, measured from the plan rectangles',
            3.2, 'ls', True)
    cols = [('Room', 70, 'l'), ('Type', 28, 'l'), ('Area m²', 20, 'r'), ('Cum. m²', 20, 'r')]
    rows = []
    tot_net = 0.0
    for lv in S['levels']:
        rows.append(['**%s   ·   FFL %+.2f' % (lv['name'].title(), lv['z']), '', '**', '**'])
        cum = 0.0
        for nm, kind, a2 in sorted(schedule(S, lv), key=lambda t: (t[1] != 'hab', t[0])):
            cum += a2
            rows.append(['   ' + nice(nm), KIND.get(kind, KIND['hab'])[2].title(),
                         '%.1f' % a2, '%.1f' % cum])
        net = net_area(S, lv)
        tot_net += net
        rows.append(['   **Level total, enclosed', '', '**%.1f' % net, ''])
    sh.table(MARG, 32, 138, cols, rows, size=1.95, rh=3.4, head=0)

    y = 34 + len(rows) * 3.4 + 10
    rows2 = []
    for i, lv in enumerate(S['levels']):
        rows2.append(['Level %d — %s   (enclosed)' % (i + 1, lv['name'].title()),
                      '%.1f m²' % net_area(S, lv)])
    rows2.append(['**Total enclosed floor area', '**%.1f m²' % tot_net])
    sh.table(MARG, y, 138, [('AREA SUMMARY', 100, 'l'), ('Area', 38, 'r')], rows2,
             size=1.95, rh=3.4, head=0)

    y += 4 + len(rows2) * 3.4 + 12
    rows3 = []
    for lab, rate in (('Basic build — 4.9 M VND/m²', 4.9),
                      ('Mid build — 6.5 M VND/m²', 6.5),
                      ('High build — 8.5 M VND/m²', 8.5)):
        rows3.append([lab, '{:,}'.format(int(round(tot_net * rate))).replace(',', ' '),
                      '{:,}'.format(int(round(tot_net * rate * 1.1))).replace(',', ' ')])
    sh.table(MARG, y, 138, [('INDICATIVE BUILD COST', 66, 'l'),
                            ('M VND', 32, 'r'), ('+10% prov.', 40, 'r')],
             rows3, title='', size=1.95, rh=3.4, head=0)
    sh.text(MARG, y - 5.0, 'ORDER OF COST — TURNKEY, NORTHERN VIET NAM', 2.5, 'ls', True)
    sh.notes(MARG, y + 4 + len(rows3) * 3.4 + 4, [
        'Areas are net internal floor areas computed from the room rectangles. Terraces, '
        'loggias, the rain-garden slot, the plant deck and roof gardens are excluded from '
        'the totals but shown on the plans.',
        'The build-cost range is a rule of thumb from published Vietnamese cost guides for '
        'northern Viet Nam, not a quotation. It excludes site works, boundary treatment '
        'and furniture.',
        'Confirm with a local quantity surveyor and at least two builders before '
        'committing to a budget.',
    ], w=138)

    sh.notes(196, 32, S.get('schedule_notes', []) + [
        'No habitable room here is below 2.7 m clear. The ground floor is a complete '
        'one-level home — bedroom, bathroom, living, dining and kitchen all at %+.2f — so '
        'the family can live on one level for as long as they want to.'
        % S['levels'][0]['z'],
        'Order-of-cost at 4.9–8.5 M VND/m² turnkey (northern Viet Nam) is in the table on the '
        'left. It is a rule of thumb, not a quotation.',
    ], w=206)
    sh.key(196, 104, KEY_ITEMS, title='ROOM TYPE KEY')
    sh.title_block(S, 'as noted', 'area schedule')
    return sh


# --------------------------------------------------------------------- index --

def draw_index(sh, S, sheets, imgdir=None, sheet_no=None):
    sh.title = S['title'] + '  ·  COVER'
    sh.sheet_no = sheet_no or '%s-05' % S['key']
    sh.frame()
    sh.text(MARG, 26, S['title'], 7.4, 'ls', True)
    sh.text(MARG, 34.5, S['tagline'], 3.0, 'ls', c=GREY)

    lv = S['levels']
    tot = sum(net_area(S, lv_) for lv_ in lv)
    g = S.get('grocery_route')
    rl = 0.0
    if g:
        rl = sum(((g[i + 1][0] - g[i][0]) ** 2 + (g[i + 1][1] - g[i][1]) ** 2) ** 0.5
                 for i in range(len(g) - 1))
    rf = S['massing']['roofs']
    figures = [
        ('Enclosed floor area', '%.0f m² over %d levels' % (tot, len(lv))),
        ('Footprint', '%.1f × %.1f m' % (S['footprint'][2] - S['footprint'][0],
                                        S['footprint'][3] - S['footprint'][1])),
        ('Clear heights', '%s' % ' · '.join('%.2f' % (l['ztop'] - l['z']) for l in lv)),
        ('Eaves / ridge', '%+.2f / %+.2f m' % (min(r['ze'] for r in rf),
                                               max(r['zr'] for r in rf))),
        ('Order of cost', '%s–%s M VND at 4.9–8.5 M VND/m² turnkey'
         % ('{:,}'.format(int(round(tot * 4.9))).replace(',', ' '),
            '{:,}'.format(int(round(tot * 8.5))).replace(',', ' '))),
    ]
    y = 46
    sh.text(MARG, y, 'THE OPTION IN NUMBERS', 2.6, 'ls', True)
    y += 5.0
    for k, v in figures:
        sh.text(MARG, y, k, 2.3, 'ls', True)
        sh.text(MARG + 44, y, v, 2.3, 'ls', c=GREY)
        sh.line((MARG, y + 1.7), (MARG + 150, y + 1.7), 0.12, (214, 209, 199))
        y += 4.6

    y += 5
    sh.text(MARG, y, 'THE IDEA', 2.6, 'ls', True)
    sh.notes(MARG, y + 5, [S.get('idea', '')], w=150, title='', size=2.2, lh=3.1, c=INK)

    y += 5 + 3.6 * (1 + len(S.get('idea', '')) // 95 + 1) + 8
    sh.text(MARG, y, 'SHEETS IN THIS SET', 2.6, 'ls', True)
    y += 5.0
    for no, nm, note in sheets:
        sh.text(MARG, y, no, 2.3, 'ls', True)
        sh.text(MARG + 20, y, nm, 2.3, 'ls')
        sh.text(MARG + 88, y, note[:46], 2.0, 'ls', c=GREY)
        sh.line((MARG, y + 1.8), (MARG + 150, y + 1.8), 0.12, (222, 217, 208))
        y += 4.4

    # render thumbnails
    if imgdir:
        shots = [('massing.png', 'clay massing study'),
                 ('street.png', 'street view, full materials'),
                 ('aerial.png', 'aerial, full materials')]
        bx, bw2 = 176.0, 116.0
        byy = 24.0
        for fn, cap in shots:
            fp_ = os.path.join(imgdir, fn)
            if not os.path.exists(fp_):
                continue
            im = Image.open(fp_).convert('RGB')
            h2 = bw2 * im.height / im.width
            im = im.resize((int(bw2 * sh.k), int(h2 * sh.k)), Image.LANCZOS)
            sh.rect(bx - 1.0, byy - 1.0, bw2 + 2, h2 + 2, None, LGREY, 0.25)
            sh.im.paste(im, (int(sh.px(bx)), int(sh.px(byy))))
            sh.text(bx, byy + h2 + 1.2, cap, 2.0, 'ls', c=GREY, italic=True)
            byy += h2 + 8.0
    sh.notes(302, 24, S.get('index_notes', []) + NOTES_COMMON, w=A3W - MARG - 302 - 2)
    sh.key(302, 74, KEY_ITEMS, title='ROOM TYPE KEY')
    sh.title_block(S, 'see each sheet', 'cover / index')
    return sh


# ------------------------------------------------------------------------ api --

NOTES_COMMON = [
    'CONCEPT ONLY — NOT FOR CONSTRUCTION. Dimensions are taken from owner-supplied title '
    'information; no survey. Subject to survey, legal merger, setbacks and permits.',
    'Areas are measured from the room rectangles; the balcony and light court are '
    'excluded from enclosed area.',
]


def render(S, outdir, dpi=200):
    """Write the whole sheet set for one scheme.  Sheet numbers are sequential
    in reading order (site, plans, top level / roof, section, schedule) so a
    two-level option does not collide with a three-level one."""
    os.makedirs(outdir, exist_ok=True)
    files = []
    n = [0]

    def num():
        n[0] += 1
        return '%s-%02d' % (S['key'], n[0])

    sheets = []

    def save(sh, filename, sheet_id, name, note):
        files.append(sh.save(os.path.join(outdir, filename)))
        sheets.append((sheet_id, name, note))

    sh = Sheet(dpi=dpi)
    draw_site(sh, S, num())
    save(sh, '01_site.png', '%s-00' % S['key'], 'Site plan',
         'existing site, zones, grocery route')

    lv = S['levels']
    sh = Sheet(dpi=dpi)
    draw_plan_sheet(sh, S, [('plan', i, i) for i in range(min(2, len(lv)))], num(),
                    'FLOOR PLANS  1–%d' % min(2, len(lv)))
    save(sh, '02_plans_a.png', '%s-01' % S['key'], 'Floor plans 1–2',
         ' · '.join(lv[i]['name'].title() for i in range(min(2, len(lv)))))

    if len(lv) > 2:
        sh = Sheet(dpi=dpi)
        draw_plan_sheet(sh, S, [('plan', 2, 2), ('roof', None, None)], num(),
                        'FLOOR PLAN 3  +  ROOF PLAN')
        save(sh, '03_plan_roof.png', '%s-02' % S['key'], 'Floor plan 3 + roof plan',
             lv[2]['name'].title() + ', then the roof over the whole house')
    else:
        sh = Sheet(dpi=dpi)
        draw_roof(sh, S, num())
        save(sh, '03_roof.png', '%s-02' % S['key'], 'Roof plan',
             'ridges, hips, eaves')

    sh = Sheet(dpi=dpi)
    draw_section(sh, S, S.get('section_cut', 8.6), num())
    save(sh, '04_section.png', '%s-03' % S['key'], 'Section A–A',
         'levels, heights, roof profile')

    sh = Sheet(dpi=dpi)
    draw_schedule(sh, S, num())
    save(sh, '05_schedule.png', '%s-04' % S['key'], 'Area schedule',
         'net areas per level, total and order of cost')

    sh = Sheet(dpi=dpi)
    draw_index(sh, S, sheets, imgdir=os.path.dirname(os.path.abspath(outdir)),
               sheet_no='%s-05' % S['key'])
    p = sh.save(os.path.join(outdir, '00_index.png'))
    files.insert(0, p)
    return files


def main(argv):
    import importlib
    mod_name, outdir = argv[0], argv[1]
    dpi = 200
    if '--dpi' in argv:
        dpi = int(argv[argv.index('--dpi') + 1])
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    S = importlib.import_module('schemes.%s' % mod_name).SCHEME
    for f in render(S, outdir, dpi):
        print('sheet:', f)
    print('SHEETS_OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
