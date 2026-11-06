#!/usr/bin/env python3
"""Procedural tileable textures (1 texture = 1 m x 1 m) for the Unity materials.
    python3 pipeline/textures.py HomeWalk/Assets/Home/Textures
"""
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

N = 512
rnd = random.Random(7)


def noise(img, amt=14, blur=0.8):
    px = img.load()
    for y in range(N):
        for x in range(N):
            r, g, b = px[x, y][:3]
            d = rnd.randint(-amt, amt)
            px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur else img


def jitter(c, a=12):
    d = rnd.randint(-a, a)
    return tuple(max(0, min(255, v + d + rnd.randint(-4, 4))) for v in c)


def bricks(base, mortar, bw=0.23, bh=0.075, m=0.012, amt=16):
    im = Image.new('RGB', (N, N), mortar)
    dr = ImageDraw.Draw(im)
    rows = round(1 / (bh + m))
    rh = N / rows
    cols = round(1 / (bw + m))
    cw = N / cols
    for r in range(rows):
        off = (cw / 2) if r % 2 else 0
        for c in range(-1, cols + 1):
            x0 = c * cw + off
            y0 = r * rh
            col = jitter(base, amt)
            mp = m * N
            for dx in (-N, 0, N):
                dr.rectangle([x0 + dx + mp / 2, y0 + mp / 2, x0 + dx + cw - mp / 2, y0 + rh - mp / 2], fill=col)
    return noise(im, 10, 0.6)


def tiles_roof(base):
    im = Image.new('RGB', (N, N), tuple(int(v * 0.55) for v in base))
    dr = ImageDraw.Draw(im)
    rows, cols = 4, 5
    rh, cw = N / rows, N / cols
    for r in range(rows):
        off = (cw / 2) if r % 2 else 0
        for c in range(-1, cols + 1):
            x0 = c * cw + off
            col = jitter(base, 14)
            for dx in (-N, 0, N):
                # curved tile: lighter band at top, darker lip at bottom
                dr.rectangle([x0 + dx + 3, r * rh + 2, x0 + dx + cw - 3, r * rh + rh - 4], fill=col)
                dr.rectangle([x0 + dx + 3, r * rh + rh - 16, x0 + dx + cw - 3, r * rh + rh - 4],
                             fill=tuple(int(v * 0.8) for v in col))
                dr.line([x0 + dx + cw / 2, r * rh + 6, x0 + dx + cw / 2, r * rh + rh - 18],
                        fill=tuple(min(255, int(v * 1.12)) for v in col), width=10)
    return noise(im, 10, 0.8)


def boards(base, w=0.12, vertical=True):
    im = Image.new('RGB', (N, N), base)
    dr = ImageDraw.Draw(im)
    n = round(1 / w)
    bw = N / n
    for i in range(n):
        col = jitter(base, 14)
        dr.rectangle([i * bw, 0, (i + 1) * bw - 3, N], fill=col)
        for k in range(14):
            x = i * bw + rnd.uniform(4, bw - 6)
            dr.line([x, 0, x + rnd.uniform(-3, 3), N], fill=jitter(tuple(int(v * 0.88) for v in col), 6), width=1)
        dr.rectangle([(i + 1) * bw - 3, 0, (i + 1) * bw, N], fill=tuple(int(v * 0.45) for v in base))
    im = noise(im, 8, 0.5)
    return im if vertical else im.rotate(90)


def floor_tiles(base, size=0.6, grout=(150, 140, 125)):
    im = Image.new('RGB', (N, N), grout)
    dr = ImageDraw.Draw(im)
    n = round(1 / size) if size < 1 else 1
    n = max(1, round(1 / size))
    s = N / n
    for i in range(n):
        for j in range(n):
            dr.rectangle([i * s + 2, j * s + 2, (i + 1) * s - 2, (j + 1) * s - 2], fill=jitter(base, 6))
    return noise(im, 7, 0.7)


def flat(base, amt=10, blur=1.2):
    return noise(Image.new('RGB', (N, N), base), amt, blur)


def grass():
    im = flat((86, 118, 52), 26, 0.4)
    dr = ImageDraw.Draw(im)
    for _ in range(4000):
        x, y = rnd.randrange(N), rnd.randrange(N)
        dr.line([x, y, x + rnd.randint(-2, 2), y - rnd.randint(3, 8)], fill=jitter((96, 140, 58), 22))
    return im


def main(out):
    os.makedirs(out, exist_ok=True)
    T = {
        'brick': bricks((132, 62, 40), (150, 132, 115)),
        'breeze': bricks((150, 78, 52), (160, 140, 120), bw=0.19, bh=0.19, m=0.02),
        'tile_roof': tiles_roof((172, 74, 40)),
        'timber': boards((112, 68, 38)),
        'timber_dk': boards((62, 38, 22), w=0.15),
        'plaster': flat((214, 204, 186), 8, 1.4),
        'plaster_w': flat((232, 226, 214), 6, 1.6),
        'cement_tile': floor_tiles((196, 186, 168), 0.6),
        'terracotta': floor_tiles((168, 92, 58), 0.4, grout=(120, 80, 60)),
        'paver': bricks((150, 140, 124), (110, 104, 96), bw=0.2, bh=0.1, m=0.01, amt=10),
        'stone': flat((152, 148, 136), 16, 0.8),
        'stone_dk': flat((105, 100, 92), 16, 0.8),
        'grass': grass(),
        'gravel': flat((150, 142, 126), 40, 0.3),
        'asphalt': flat((52, 52, 54), 18, 0.3),
        'soil': flat((70, 50, 32), 22, 0.5),
        'existing': flat((158, 158, 154), 6, 1.0),
    }
    for k, im in T.items():
        im.save(os.path.join(out, k + '.png'))
        print('tex', k)


if __name__ == '__main__':
    main(sys.argv[1])
