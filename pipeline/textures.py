#!/usr/bin/env python3
"""Procedural tileable PBR-ish textures (1 texture = 1 m x 1 m) for the Unity materials.
Each material gets:
  <name>.png    albedo (RGB) + smoothness variation (A, multiplied by the material's smoothness)
  <name>_n.png  tangent-space normal map (OpenGL / Unity convention, +Y up) from a height field
    python3 pipeline/textures.py HomeWalk/Assets/Home/Textures
"""
import os
import sys

import numpy as np
from PIL import Image

N = 1024
rng = np.random.default_rng(7)
YY, XX = np.mgrid[0:N, 0:N] / N          # v (rows, top-down), u (cols) in 0..1


def vnoise(cx, cy=None):
    """Tileable value noise with cx x cy cells over the tile, 0..1."""
    cy = cy or cx
    a = rng.random((cy, cx)).astype(np.float32)
    t = np.tile(a, (3, 3))
    im = Image.fromarray(t).resize((3 * N, 3 * N), Image.BICUBIC)
    return np.clip(np.asarray(im)[N:2 * N, N:2 * N], 0, 1)


def fbm(c0=4, octaves=5, gain=0.5, cy_ratio=1.0):
    out, amp, tot = np.zeros((N, N), np.float32), 1.0, 0.0
    c = c0
    for _ in range(octaves):
        out += amp * vnoise(c, max(1, int(round(c * cy_ratio))))
        tot += amp
        amp *= gain
        c *= 2
    return out / tot


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def col(c):
    return np.array(c, np.float32) / 255.0


def grid(rows, cols, stagger=0.5):
    """Running-bond grid: returns cell ids and local coords (0..1) inside each cell."""
    r = np.floor(YY * rows).astype(int)
    off = np.where(r % 2 == 1, stagger, 0.0)
    u = XX * cols + off
    c = np.floor(u).astype(int) % cols
    lu, lv = u - np.floor(u), YY * rows - r
    return r, c, lu, lv


def per_cell(r, c, rows, cols, n=3, spread=1.0):
    """Per-cell variation: mostly brightness, with only a small hue shift (n=3), or a scalar (n=1)."""
    lum = rng.normal(0, spread, (rows, cols, 1)).astype(np.float32)
    tab = lum if n == 1 else lum + rng.normal(0, spread * 0.15, (rows, cols, 3)).astype(np.float32)
    return tab[r % rows, c % cols]


def bricks(base, mortar, bw=0.23, bh=0.075, m=0.012, var=0.08, stagger=0.5):
    rows, cols = round(1 / (bh + m)), round(1 / (bw + m))
    r, c, lu, lv = grid(rows, cols, stagger)
    mu, mv = m * cols / 2, m * rows / 2              # mortar half-width in local units
    edge = np.minimum(np.minimum(lu, 1 - lu) / mu, np.minimum(lv, 1 - lv) / mv)
    face = smooth(0.8, 1.6, edge)                    # 0 in mortar, 1 on the brick face, bevelled
    jit = per_cell(r, c, rows, cols, 3, var)
    tone = per_cell(r, c, rows, cols, 1, 0.07)
    grime = fbm(6, 5)
    speck = fbm(48, 3)
    b = col(base)[None, None, :] * (1 + tone) + jit * 0.35
    b = b * (0.86 + 0.28 * speck[..., None]) * (0.9 + 0.12 * grime[..., None])
    mo = col(mortar)[None, None, :] * (0.88 + 0.2 * fbm(32, 3)[..., None])
    alb = mo * (1 - face[..., None]) + b * face[..., None]
    h = face * (0.85 + 0.15 * speck) + 0.05 * fbm(64, 2)
    gloss = 0.5 + 0.4 * face
    return alb, h, gloss, 3.0


def roof_tiles(base):
    rows, cols = 4, 5
    r, c, lu, lv = grid(rows, cols)
    jit = per_cell(r, c, rows, cols, 3, 0.05)
    barrel = np.sin(lu * np.pi) ** 0.6                      # curved tile across its width
    lip = smooth(0.82, 0.9, lv) * (1 - smooth(0.93, 0.99, lv))
    h = barrel * (0.6 + 0.4 * (1 - lv)) + 0.35 * lip
    shade = 0.62 + 0.38 * barrel
    alb = (col(base)[None, None, :] + jit) * shade[..., None] * (0.85 + 0.3 * fbm(8, 4)[..., None])
    return alb, h, 0.4 + 0.5 * barrel, 4.0


def boards(base, w=0.12, groove=0.02, vertical=True, grain=True, var=0.06, gdark=0.45):
    n = round(1 / w)
    u, v = (XX, YY) if vertical else (YY, XX)
    i = np.floor(u * n).astype(int)
    lu = u * n - i
    gw = groove * n
    edge = np.minimum(lu, 1 - lu) / gw
    face = smooth(0.6, 1.4, edge)
    tab = rng.normal(0, var, (n, 1)).astype(np.float32) + rng.normal(0, var * 0.15, (n, 3)).astype(np.float32)
    jit = tab[i % n]
    if grain:
        g = fbm(64, 4, cy_ratio=1 / 32) if vertical else fbm(2, 4, cy_ratio=32)
        streak = 0.82 + 0.3 * g
    else:
        streak = 0.95 + 0.08 * fbm(16, 3)
    alb = (col(base)[None, None, :] + jit) * streak[..., None]
    alb = alb * (gdark + (1 - gdark) * face[..., None])
    h = face * (0.9 + 0.1 * streak)
    return alb, h, 0.35 + 0.6 * face, 2.5


def floor_tiles(base, size=0.6, grout=(150, 140, 125), var=0.025, bump=2.0):
    n = max(1, round(1 / size))
    r, c, lu, lv = grid(n, n, stagger=0.0)
    gw = 0.004 * n
    edge = np.minimum(np.minimum(lu, 1 - lu), np.minimum(lv, 1 - lv)) / gw
    face = smooth(0.7, 1.6, edge)
    jit = per_cell(r, c, n, n, 3, var)
    cloud = fbm(5, 5)
    t = (col(base)[None, None, :] + jit) * (0.93 + 0.12 * cloud[..., None])
    alb = col(grout)[None, None, :] * (1 - face[..., None]) + t * face[..., None]
    h = face + 0.02 * fbm(64, 2)
    return alb, h, 0.25 + 0.75 * face, bump


def stucco(base, amt=0.05, rough=1.0):
    big, fine = fbm(4, 5), fbm(96, 3)
    alb = col(base)[None, None, :] * (1 - amt + 2 * amt * big[..., None]) * (0.97 + 0.05 * fine[..., None])
    h = 0.6 * fine + 0.4 * fbm(192, 2)
    return alb, h, 0.6 + 0.4 * (1 - fine), rough


def stone(base, amt=0.18):
    a, b = fbm(6, 6), fbm(40, 3)
    alb = col(base)[None, None, :] * (1 - amt + 2 * amt * a[..., None]) * (0.88 + 0.22 * b[..., None])
    return alb, 0.6 * b + 0.4 * a, 0.5 + 0.5 * a, 2.5


def pebbles(base, cells=70, var=0.2):
    # jittered voronoi: each pixel takes the nearest of a jittered grid of stones (tileable)
    g = cells
    pts = (np.stack(np.mgrid[0:g, 0:g], -1) + rng.random((g, g, 2))) / g
    tone = rng.normal(0, var, (g, g, 1)).astype(np.float32) + rng.normal(0, var * 0.2, (g, g, 3)).astype(np.float32)
    gy, gx = np.floor(YY * g).astype(int), np.floor(XX * g).astype(int)
    best = np.full((N, N), 9.0, np.float32)
    second = np.full((N, N), 9.0, np.float32)
    bt = np.zeros((N, N, 3), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cy, cx = (gy + dy) % g, (gx + dx) % g
            p = pts[cy, cx]
            py, px = p[..., 0] + np.floor((gy + dy) / g), p[..., 1] + np.floor((gx + dx) / g)
            d = np.hypot(YY - py, XX - px).astype(np.float32)
            closer = d < best
            second = np.where(closer, best, np.minimum(second, d))
            bt = np.where(closer[..., None], tone[cy, cx], bt)
            best = np.where(closer, d, best)
    edge = (second - best) * g
    h = smooth(0.0, 0.5, edge)
    alb = (col(base)[None, None, :] * (1 + bt)) * (0.5 + 0.5 * h[..., None])
    return alb, h, 0.3 + 0.4 * h, 3.0


def grass():
    a, b, c = fbm(6, 5), fbm(128, 2), fbm(256, 1)
    g1, g2, dry = col((70, 108, 42)), col((104, 140, 58)), col((140, 136, 80))
    alb = g1 * (1 - b[..., None]) + g2 * b[..., None]
    alb = alb * (1 - 0.25 * smooth(0.6, 0.8, a)[..., None]) + dry * 0.25 * smooth(0.6, 0.8, a)[..., None]
    alb = alb * (0.75 + 0.35 * c[..., None])
    return alb, 0.5 * b + 0.5 * c, 0.2 + 0.2 * c, 2.0


def asphalt():
    a, b = fbm(4, 5), fbm(200, 2)
    alb = col((52, 52, 54))[None, None, :] * (0.85 + 0.25 * a[..., None]) * (0.75 + 0.5 * b[..., None])
    return alb, b, 0.3 + 0.3 * a, 1.5


def soil():
    a, b = fbm(5, 5), fbm(90, 3)
    alb = col((74, 54, 34))[None, None, :] * (0.75 + 0.4 * a[..., None]) * (0.8 + 0.3 * b[..., None])
    return alb, 0.4 * a + 0.6 * b, 0.15 + 0.2 * a, 2.0


def normal_map(h, strength):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength * N / 64
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength * N / 64
    n = np.stack([-gx, gy, np.ones_like(h)], -1)          # image rows go down = -v, so +gy flips to +Y up
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def save(out, name, alb, h, gloss, strength):
    a = np.clip(alb, 0, 1)
    g = np.clip(np.broadcast_to(gloss, h.shape), 0, 1)
    rgba = np.dstack([(a * 255).astype(np.uint8), (g * 255).astype(np.uint8)])
    Image.fromarray(rgba, 'RGBA').save(os.path.join(out, name + '.png'))
    hn = (h - h.min()) / max(1e-6, h.max() - h.min())
    Image.fromarray(normal_map(hn.astype(np.float32), strength), 'RGB').save(os.path.join(out, name + '_n.png'))


def main(out):
    os.makedirs(out, exist_ok=True)
    T = {
        'brick': lambda: bricks((150, 66, 42), (176, 166, 150)),
        'breeze': lambda: bricks((158, 82, 54), (170, 150, 128), bw=0.19, bh=0.19, m=0.02),
        'tile_roof': lambda: roof_tiles((172, 74, 40)),
        'timber': lambda: boards((118, 72, 40), w=0.14, groove=0.012),
        'timber_dk': lambda: boards((66, 40, 24), w=0.15, groove=0.012),
        'plaster': lambda: stucco((216, 206, 188), 0.04, 0.22),
        'plaster_w': lambda: stucco((236, 232, 222), 0.03, 0.18),
        'render_w': lambda: stucco((238, 236, 230), 0.035, 0.55),
        'clad_v': lambda: boards((240, 240, 236), w=0.15, groove=0.006, grain=False, var=0.01, gdark=0.72),
        'cement_tile': lambda: floor_tiles((206, 198, 184), 0.6),
        'terracotta': lambda: floor_tiles((172, 96, 60), 0.4, grout=(126, 98, 78), var=0.06),
        'paver': lambda: bricks((158, 148, 130), (112, 106, 98), bw=0.2, bh=0.1, m=0.008, var=0.05),
        'stone': lambda: stone((156, 152, 140)),
        'stone_dk': lambda: stone((96, 92, 86), 0.22),
        'grass': grass,
        'gravel': lambda: pebbles((156, 148, 132)),
        'asphalt': asphalt,
        'soil': soil,
        'existing': lambda: stucco((160, 160, 156), 0.08, 0.5),
    }
    only = set(sys.argv[2:])
    for k, f in T.items():
        if only and k not in only:
            continue
        save(out, k, *f())
        print('tex', k)


if __name__ == '__main__':
    main(sys.argv[1])
