"""Concept JSON -> Blender model, FBX for Unity, and Cycles views.

    blender -b --factory-startup --python pipeline/blender/build.py -- \
        concepts/c1_courtyard_house.json out/c1 [--fast] [--no-render] [--fbx path.fbx]

Collections: L0, L1 (walls/floors/ceilings per level), GLASS, STAIR, ROOF, PORCH,
FENCE, SITE (ground, road, river, existing NW building), TREES (render only).
FBX export joins objects per collection+material -> '<COLL>__<material>' so Unity
can remap materials by name and toggle the roof/upper floor.
"""
import bpy
import math
import os
import sys

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
sys.path.insert(0, PIPE)

from scheme import load  # noqa: E402
from lib import bbuild as B  # noqa: E402
from lib import walls2  # noqa: E402
from lib.bbuild import box, coll  # noqa: E402

FAST = '--fast' in argv
NO_RENDER = '--no-render' in argv


# ----------------------------------------------------------------- materials --
def materials(massing=False):
    M = B.build_materials(massing=massing)
    if massing:
        for k in ('brick', 'breeze', 'asphalt', 'paver', 'soil', 'existing', 'rail', 'neigh_a', 'neigh_b'):
            M[k] = M['plaster']
        return M
    # terracotta roof of the concept image (warmer than the option-study tile)
    bpy.data.materials.remove(M['tile_roof'])
    M['tile_roof'] = B.mat('tile_roof', (0.52, 0.17, 0.08), 0.78, tex='brick', texscale=1.6)
    M['brick'] = B.mat('brick', (0.47, 0.20, 0.12), 0.88, tex='brick', texscale=2.2)
    M['breeze'] = B.mat('breeze', (0.50, 0.24, 0.15), 0.9)
    M['asphalt'] = B.mat('asphalt', (0.17, 0.17, 0.17), 0.92, tex='noise', texscale=1.5)
    M['paver'] = B.mat('paver', (0.55, 0.50, 0.44), 0.88, tex='brick', texscale=1.4)
    M['soil'] = B.mat('soil', (0.22, 0.15, 0.09), 0.97)
    M['existing'] = B.mat('existing', (0.62, 0.62, 0.60), 0.9)
    M['neigh_a'] = B.mat('neigh_a', (0.80, 0.70, 0.45), 0.9, tex='noise', texscale=0.8)
    M['neigh_b'] = B.mat('neigh_b', (0.66, 0.72, 0.74), 0.9, tex='noise', texscale=0.8)
    M['rail'] = M['timber_dk']
    # brick/tile textures read on vertical faces: rotate object-space mapping so rows run horizontally
    for k in ('brick', 'paver'):
        for n in M[k].node_tree.nodes:
            if n.type == 'MAPPING':
                n.inputs['Rotation'].default_value = (math.pi / 2, 0, 0)
    return M


# --------------------------------------------------------------------- walls --
def merge_pieces(pieces):
    """Merge collinear, touching pieces of the same type/exposure so faces never overlap."""
    groups = {}
    for p in pieces:
        k = (p['axis'], round(p['coord'], 3), p['type'], round(p['thick'], 3), p['ext'], p['side'])
        groups.setdefault(k, []).append(p)
    out = []
    for k, ps in groups.items():
        ps.sort(key=lambda q: q['t0'])
        cur = None
        for q in ps:
            if cur and abs(q['t0'] - cur['t1']) < 0.02:
                cur['t1'] = q['t1']
                cur['openings'] = cur['openings'] + q['openings']
                cur['rooms'] = cur['rooms'] + q['rooms']
            else:
                if cur:
                    out.append(cur)
                cur = dict(q, openings=list(q['openings']))
        out.append(cur)
    return out


def wall_piece(p, z0, z1, M, cn, skin=None):
    """One (merged) wall run -> boxes with storey-relative openings.
    External solid walls get an outer cladding skin (brick / timber) and a plaster inner leaf."""
    t = p['thick']
    a, b, c = p['t0'], p['t1'], p['coord']
    if p['type'] == 'solid':
        a -= t / 2
        b += t / 2
    H = z1 - z0
    layers = [(-t / 2, t / 2, None)]
    if p['type'] == 'solid' and p['ext'] and skin is not None:
        sk = 0.07
        if p['side'] == 1:      # outside towards +coord
            layers = [(-t / 2, t / 2 - sk, None), (t / 2 - sk, t / 2, skin)]
        else:
            layers = [(-t / 2 + sk, t / 2, None), (-t / 2, -t / 2 + sk, skin)]

    def bx(s0, s1, h0, h1, m):
        if s1 - s0 < 0.01 or h1 - h0 < 0.01:
            return
        for d0, d1, lm in (layers if m in (M['plaster'], M['plaster_w']) else [(-t / 2, t / 2, None)]):
            mm = lm or m
            if p['axis'] == 'x':     # runs along x at y=c
                box(s0, c + d0, z0 + h0, s1, c + d1, z0 + h1, mm, cn)
            else:
                box(c + d0, s0, z0 + h0, c + d1, s1, z0 + h1, mm, cn)

    if p['type'] == 'rail':
        hr = 1.05
        n = max(1, int(round((b - a) / 1.2)))
        for i in range(n + 1):
            s = a + (b - a) * i / n
            bx(s - 0.05, s + 0.05, 0, hr, M['timber_dk'])
        bx(a, b, hr - 0.07, hr, M['timber_dk'])
        bx(a, b, 0.08, 0.14, M['timber_dk'])
        k = int((b - a) / 0.14)
        for i in range(1, k):
            s = a + i * (b - a) / k
            bx(s - 0.015, s + 0.015, 0.14, hr - 0.07, M['timber'])
        return
    if p['type'] == 'glass':
        # timber-framed full-height glazing to the light court
        bx(a, b, 0, 0.08, M['timber_dk'])
        bx(a, b, H - 0.30, H, M['timber_dk'])
        n = max(1, int(round((b - a) / 1.0)))
        for i in range(n + 1):
            s = a + (b - a) * i / n
            bx(s - 0.04, s + 0.04, 0, H, M['timber_dk'])
        bx(a, b, 2.4, 2.46, M['timber_dk'])
        gt = 0.02
        if p['axis'] == 'x':
            box(a, c - gt, z0 + 0.08, b, c + gt, z1 - 0.30, M['glass'], 'GLASS')
        else:
            box(c - gt, a, z0 + 0.08, c + gt, b, z1 - 0.30, M['glass'], 'GLASS')
        return
    ops = sorted(p['openings'])
    cur = a
    m = M['plaster_w']
    for o0, o1, sill, head, kind in ops:
        bx(cur, o0, 0, H, m)
        bx(o0, o1, 0, sill, m)
        bx(o0, o1, head, H, m)
        cur = o1
        # frames and glazing
        fw = 0.06
        if kind in ('window', 'sldoor'):
            bx(o0, o0 + fw, sill, head, M['timber_dk'])
            bx(o1 - fw, o1, sill, head, M['timber_dk'])
            bx(o0, o1, head - fw, head, M['timber_dk'])
            if sill > 0.01:
                bx(o0 - 0.05, o1 + 0.05, sill - 0.04, sill, M['timber_dk'])
            # mullions every ~0.9 m
            k = max(1, int(round((o1 - o0) / 0.9))) if kind == 'window' else 1
            for i in range(1, k):
                s = o0 + (o1 - o0) * i / k
                bx(s - 0.03, s + 0.03, sill, head, M['timber_dk'])
            gt = 0.015
            g0, g1 = o0 + fw, o1 - fw
            if kind == 'sldoor':
                # one fixed glazed panel, the other bay slid open so the walkthrough can pass
                g1 = (o0 + o1) / 2
                bx(g1 - 0.03, g1 + 0.03, sill, head, M['timber_dk'])
            if p['axis'] == 'x':
                box(g0, c - gt, z0 + sill, g1, c + gt, z0 + head - fw, M['glass'], 'GLASS')
            else:
                box(c - gt, g0, z0 + sill, c + gt, g1, z0 + head - fw, M['glass'], 'GLASS')
        elif kind == 'door':
            bx(o0 - 0.05, o0, 0, head + 0.05, M['timber_dk'])
            bx(o1, o1 + 0.05, 0, head + 0.05, M['timber_dk'])
            bx(o0 - 0.05, o1 + 0.05, head, head + 0.05, M['timber_dk'])
    bx(cur, b, 0, H, m)


# --------------------------------------------------------------------- stair --
def build_stair(st, M):
    """U-stair: bottom landing (y0..y0+bl) -> flight 1 north (west half) -> half landing ->
    flight 2 south (east half) -> arrival slab at the upper floor over the bottom landing."""
    cn = 'STAIR'
    x0, y0, x1, y1 = st['x0'], st['y0'], st['x1'], st['y1']
    if st.get('first_dir', 'north') == 'south':
        # mirrored: bottom landing + arrival at the north side, flight 1 runs south
        def sb(xa, ya, za, xb, yb, zb, m, c):
            return box(xa, y0 + y1 - yb, za, xb, y0 + y1 - ya, zb, m, c)
    else:
        sb = box
    z0, z1, n = st['z0'], st['z1'], st['risers']
    rise = (z1 - z0) / n
    tread = st['tread']
    bl = st.get('bottom_landing', 0.75)
    half = n // 2
    xm = (x0 + x1) / 2
    ys = y0 + bl                       # first riser of flight 1
    run = (half - 1) * tread
    ya = ys + run                      # top of flight 1 / start of half landing
    zl = z0 + half * rise
    # flight 1: west half, going north, solid
    for i in range(half - 1):
        sb(x0 + 0.02, ys + i * tread, z0, xm - 0.02, ys + (i + 1) * tread, z0 + (i + 1) * rise, M['timber'], cn)
    # half landing
    sb(x0 + 0.02, ya, zl - 0.25, x1 - 0.02, y1 - 0.02, zl, M['timber'], cn)
    # flight 2: east half, from the landing going south, floating treads
    for i in range(half - 1):
        zt = zl + (i + 1) * rise
        yb = ya - (i + 1) * tread
        sb(xm + 0.02, yb, zt - 0.22, x1 - 0.02, yb + tread, zt, M['timber'], cn)
    # arrival slab at upper floor level over the bottom landing (east half)
    sb(xm + 0.02, y0 - 0.02, z1 - 0.22, x1 - 0.02, ys, z1, M['timber'], cn)
    # timber screen between flights (full height) from the first riser to the half landing
    k = int((ya - ys) / 0.12)
    for j in range(k + 1):
        y = ys + j * 0.12
        sb(xm - 0.03, y - 0.02, z0, xm + 0.03, y + 0.02, z1, M['timber_dk'], cn)
    # guard on the arrival slab's west edge (over the bottom landing void)
    for y in (y0 + 0.05, y0 + bl / 2, ys - 0.03):
        sb(xm - 0.03, y - 0.03, z1, xm + 0.03, y + 0.03, z1 + 0.95, M['timber_dk'], cn)
    sb(xm - 0.03, y0, z1 + 0.88, xm + 0.03, ys, z1 + 0.95, M['timber_dk'], cn)
    sb(xm - 0.03, y0, z1 + 0.40, xm + 0.03, ys, z1 + 0.45, M['timber_dk'], cn)


# --------------------------------------------------------------------- house --
def build_house(S, M):
    C = S['concept']
    fx0, fy0, fx1, fy1 = S['footprint']
    levels = S['levels']
    # plinth (raised ground floor), leaving the light court open to soil
    court = [r for r in levels[0]['rooms'] if r[5] == 'plant']
    z_gf = levels[0]['z']
    box(fx0, fy0, 0.0, fx1, fy1, z_gf - 0.02, M['stone_dk'], 'L0')
    for i, lv in enumerate(levels):
        cn = 'L%d' % i
        z0, z1 = lv['z'], lv['ztop']
        voids = set(lv.get('voids', ()))
        for nm, x0, y0, x1, y1, k in lv['rooms']:
            if nm in voids or k == 'plant':
                if k == 'plant' and i == 0:
                    box(x0, y0, z0 - 0.25, x1, y1, z0 - 0.05, M['soil'], cn)
                continue
            fm = M['timber'] if lv.get('floor') == 'timber' else M['cement_tile']
            if k == 'serv':
                fm = M['cement_tile']
            if k == 'out':
                fm = M['terracotta']
            thick = 0.02 if i == 0 else 0.22
            box(x0, y0, z0 - thick, x1, y1, z0, fm, cn)
            # ceiling (top level only; lower levels get the next slab's underside)
            if i == len(levels) - 1 and k != 'plant':
                box(x0, y0, z1 - 0.12, x1, y1, z1, M['timber'] if k == 'out' else M['plaster_w'], cn)
        skin = M['brick'] if i == 0 else M['timber']
        for p in merge_pieces(walls2.derive(lv)):
            wall_piece(p, z0, z1, M, cn, skin=skin)
        # upper slab edge band where lower level has no slab (court/stair void handled by walls)
    # wall-head band between top storey and roof
    zt = levels[-1]['ztop']
    ze = max(r['ze'] for r in C['roofs'] if r['x0'] <= fx0 + 0.01 and r.get('kind', 'hip') in ('hip', 'gable'))
    t = 0.25
    for (a0, b0, a1, b1) in ((fx0 - t / 2, fy0 - t / 2, fx1 + t / 2, fy0 + t / 2),
                             (fx0 - t / 2, fy1 - t / 2, fx1 + t / 2, fy1 + t / 2),
                             (fx0 - t / 2, fy0, fx0 + t / 2, fy1),
                             (fx1 - t / 2, fy0, fx1 + t / 2, fy1)):
        box(a0, b0, zt, a1, b1, ze + 0.30, M['timber_dk'], 'ROOF')
    # balcony posts on the north edge (timber, as in the concept)
    for nm, x0, y0, x1, y1, k in levels[-1]['rooms']:
        if k == 'out':
            n = max(2, int(round((x1 - x0) / 2.8)))
            for j in range(n + 1):
                x = x0 + 0.12 + (x1 - x0 - 0.24) * j / n
                box(x - 0.09, y1 - 0.2, levels[-1]['z'], x + 0.09, y1 - 0.02, ze + 0.25, M['timber_dk'], 'L1')
    # roofs
    for r in C['roofs']:
        kind = r.get('kind', 'hip')
        if kind == 'skylight':
            build_skylight(r, M)
            continue
        if kind == 'lean':
            build_lean(r, C.get('carport', {}), M)
            continue
        B.hip(r['x0'], r['y0'], r['x1'], r['y1'], r['ze'], r['zr'], M[r.get('mat', 'tile_roof')],
              'ROOF', overhang=r.get('overhang', 0.6), thick=0.12)
        o = r.get('overhang', 0.6)
        # fascia
        for (a0, b0, a1, b1) in ((r['x0'] - o, r['y0'] - o, r['x1'] + o, r['y0'] - o + 0.06),
                                 (r['x0'] - o, r['y1'] + o - 0.06, r['x1'] + o, r['y1'] + o),
                                 (r['x0'] - o, r['y0'] - o, r['x0'] - o + 0.06, r['y1'] + o),
                                 (r['x1'] + o - 0.06, r['y0'] - o, r['x1'] + o, r['y1'] + o)):
            box(a0, b0, r['ze'] - 0.22, a1, b1, r['ze'] + 0.02, M['timber_dk'], 'ROOF')
    # porch: platform, steps, posts
    p = C.get('porch')
    if p:
        box(p['x0'], p['y0'] + 0.6, 0.0, p['x1'], fy0, z_gf, M['terracotta'], 'PORCH')
        ns = p.get('steps', 3)
        for s in range(ns):
            h = z_gf * (s + 1) / (ns + 1)
            yy = p['y0'] + 0.6 - (ns - s) * 0.3 + 0.3
            box(p['x0'] + 0.6, yy - 0.3, 0.0, p['x1'] - 0.6, yy, h, M['terracotta'], 'PORCH')
        for (x, y) in p['posts']:
            box(x - 0.12, y + 0.4, z_gf, x + 0.12, y + 0.64, p.get('post_top', C['roofs'][1]['ze']), M['timber_dk'], 'PORCH')
            box(x - 0.2, y + 0.32, z_gf, x + 0.2, y + 0.72, z_gf + 0.3, M['stone'], 'PORCH')
    if C.get('stair'):
        build_stair(C['stair'], M)


def build_skylight(r, M):
    """Flat roof strip between two pitched roofs with a raised glazed lantern over r['glass']."""
    cn = 'ROOF'
    x0, y0, x1, y1, ze, zr = r['x0'], r['y0'], r['x1'], r['y1'], r['ze'], r['zr']
    gx0, gy0, gx1, gy1 = r['glass']
    zd = ze + 0.25                      # roof deck
    # deck around the lantern opening
    box(x0, y0, zd - 0.2, gx0, y1, zd, M['tile_roof'], cn)
    box(gx1, y0, zd - 0.2, x1, y1, zd, M['tile_roof'], cn)
    box(gx0, y0, zd - 0.2, gx1, gy0, zd, M['tile_roof'], cn)
    box(gx0, gy1, zd - 0.2, gx1, y1, zd, M['tile_roof'], cn)
    # lantern: timber frame, glass sides and top
    for (a0, b0, a1, b1) in ((gx0 - 0.1, gy0 - 0.1, gx1 + 0.1, gy0), (gx0 - 0.1, gy1, gx1 + 0.1, gy1 + 0.1),
                             (gx0 - 0.1, gy0, gx0, gy1), (gx1, gy0, gx1 + 0.1, gy1)):
        box(a0, b0, zd, a1, b1, zd + 0.15, M['timber_dk'], cn)
        box(a0, b0, zr - 0.1, a1, b1, zr, M['timber_dk'], cn)
    for (xx, yy) in ((gx0, gy0), (gx1, gy0), (gx0, gy1), (gx1, gy1)):
        box(xx - 0.06, yy - 0.06, zd, xx + 0.06, yy + 0.06, zr, M['timber_dk'], cn)
    box(gx0, gy0, zr - 0.04, gx1, gy1, zr - 0.01, M['glass'], 'GLASS')
    box(gx0, gy0 - 0.02, zd + 0.15, gx1, gy0 + 0.02, zr - 0.1, M['glass'], 'GLASS')
    box(gx0, gy1 - 0.02, zd + 0.15, gx1, gy1 + 0.02, zr - 0.1, M['glass'], 'GLASS')
    box(gx0 - 0.02, gy0, zd + 0.15, gx0 + 0.02, gy1, zr - 0.1, M['glass'], 'GLASS')
    box(gx1 - 0.02, gy0, zd + 0.15, gx1 + 0.02, gy1, zr - 0.1, M['glass'], 'GLASS')
    k = max(1, int((gy1 - gy0) / 0.9))
    for i in range(1, k):
        yy = gy0 + (gy1 - gy0) * i / k
        box(gx0, yy - 0.03, zr - 0.08, gx1, yy + 0.03, zr, M['timber_dk'], cn)
    # light-well lining through the roof space down to the upper ceiling
    for (a0, b0, a1, b1) in ((gx0 - 0.06, gy0 - 0.06, gx1 + 0.06, gy0), (gx0 - 0.06, gy1, gx1 + 0.06, gy1 + 0.06),
                             (gx0 - 0.06, gy0, gx0, gy1), (gx1, gy0, gx1 + 0.06, gy1)):
        box(a0, b0, ze - 0.2, a1, b1, zd, M['plaster_w'], cn)


def build_lean(r, cp, M):
    """Lean-to carport roof falling west, on timber posts and a beam."""
    cn = 'ROOF'
    x0, y0, x1, y1, zl, zh = r['x0'], r['y0'], r['x1'], r['y1'], r['zlow'], r['zhigh']
    B._plate([(x0, y0, zl), (x1, y0, zh), (x1, y1, zh), (x0, y1, zl)], 0.1, M[r.get('mat', 'tile_roof')], cn)
    px = cp.get('posts_x', x0 + 0.15)
    step = cp.get('post_step', 3.0)
    n = max(1, int(round((y1 - y0) / step)))
    zp = zl + (zh - zl) * (px - x0) / max(0.01, x1 - x0) - 0.12
    for i in range(n + 1):
        y = y0 + 0.12 + (y1 - y0 - 0.24) * i / n
        box(px - 0.1, y - 0.1, 0, px + 0.1, y + 0.1, zp, M['timber_dk'], 'PORCH')
        box(px - 0.2, y - 0.2, 0, px + 0.2, y + 0.2, 0.25, M['stone'], 'PORCH')
    box(px - 0.08, y0, zp - 0.25, px + 0.08, y1, zp, M['timber_dk'], 'PORCH')       # beam
    box(x0 - 0.02, y0, zl - 0.22, x0 + 0.05, y1, zl + 0.02, M['timber_dk'], cn)     # fascia
    box(x0, y0 - 0.05, zl - 0.2, x1, y0 + 0.01, zh, M['timber_dk'], cn)            # front fascia


# --------------------------------------------------------------------- fence --
def build_fence(S, M):
    C, W = S['concept'], S['site']['site']['width']
    f = C.get('fence', {})
    cn = 'FENCE'
    fr = f.get('front')
    if fr and 'gates' in fr:
        build_front_gates(fr, W, M, cn)
    elif fr:
        y, h = fr['y'], fr['height']
        g0, g1 = fr['gate']
        p0, p1 = fr['passage_gate']
        spans = [(0.0, p0), (p1, g0), (g1, W)]
        for a, b in spans:
            if b - a < 0.05:
                continue
            box(a, y - 0.11, 0, b, y + 0.11, 0.9, M['brick'], cn)       # base
            box(a, y - 0.13, h - 0.08, b, y + 0.13, h, M['stone'], cn)   # coping
            # piers every ~1.6 m, breeze-block lattice between
            n = max(1, int(round((b - a) / 1.6)))
            for i in range(n + 1):
                x = a + (b - a) * i / n
                box(x - 0.18, y - 0.18, 0, x + 0.18, y + 0.18, h + 0.12, M['brick'], cn)
            if fr.get('breeze_panels'):
                for i in range(n):
                    xa = a + (b - a) * i / n + 0.18
                    xb = a + (b - a) * (i + 1) / n - 0.18
                    k = max(1, int((xb - xa) / 0.2))
                    for j in range(k + 1):
                        xx = xa + (xb - xa) * j / k
                        box(xx - 0.03, y - 0.06, 0.9, xx + 0.03, y + 0.06, h - 0.08, M['breeze'], cn)
                    for zz in (1.12, 1.36, 1.6):
                        box(xa, y - 0.06, zz - 0.03, xb, y + 0.06, zz + 0.03, M['breeze'], cn)
        # gate: two timber leaves standing open (inward) so the walkthrough can pass
        L = (g1 - g0) / 2
        box(g0 - 0.02, y + 0.1, 0.05, g0 + 0.06, y + 0.1 + L * 0.95, 1.8, M['timber_dk'], cn)
        box(g1 - 0.06, y + 0.1, 0.05, g1 + 0.02, y + 0.1 + L * 0.95, 1.8, M['timber_dk'], cn)
        box(g0 - 0.25, y - 0.25, 0, g0, y + 0.25, h + 0.5, M['brick'], cn)
        box(g1, y - 0.25, 0, g1 + 0.25, y + 0.25, h + 0.5, M['brick'], cn)
        # gate canopy (small tiled hood, inside ONT)
        box(g0 - 0.3, y - 0.3, h + 0.5, g1 + 0.3, y + 0.35, h + 0.62, M['tile_roof'], cn)
        # lamps on gate piers
        for x in (g0 - 0.125, g1 + 0.125):
            box(x - 0.09, y - 0.32, h - 0.1, x + 0.09, y - 0.25, h + 0.2, M['white'], cn)
        # passage door (timber)
        box(p0, y - 0.04, 0.02, p1, y + 0.04, 1.8, M['timber_dk'], cn)
    sd = f.get('sides')
    if sd:
        y0 = fr['y'] + 0.2 if fr else 0.0
        h = sd['height']
        for side, x in (('west', 0.11), ('east', W - 0.11)):
            # split the run around any breaks (e.g. the existing NW building forms the boundary there)
            spans, cur = [], y0
            for bside, b0, b1 in sorted(b for b in sd.get('breaks', []) if b[0] == side):
                if b0 > cur:
                    spans.append((cur, b0))
                cur = max(cur, b1)
            if sd['y1'] > cur:
                spans.append((cur, sd['y1']))
            for a, b in spans:
                box(x - 0.11, a, 0, x + 0.11, b, 0.9, M['brick'], cn)
                box(x - 0.13, a, h - 0.08, x + 0.13, b, h, M['stone'], cn)
                n = max(1, int(round((b - a) / 2.4)))
                for i in range(n + 1):
                    y = a + (b - a) * i / n
                    box(x - 0.18, y - 0.18, 0, x + 0.18, y + 0.18, h + 0.1, M['brick'], cn)
                for i in range(n):
                    ya_ = a + (b - a) * i / n + 0.18
                    yb_ = a + (b - a) * (i + 1) / n - 0.18
                    if sd.get('breeze_panels') and ya_ > 19.7:
                        # open breeze-block panels along the garden: light and river breeze through
                        k = max(1, int((yb_ - ya_) / 0.2))
                        for j in range(k + 1):
                            yy = ya_ + (yb_ - ya_) * j / k
                            box(x - 0.06, yy - 0.03, 0.9, x + 0.06, yy + 0.03, h - 0.08, M['breeze'], cn)
                        for zz in (1.12, 1.36, 1.6):
                            box(x - 0.06, ya_, zz - 0.03, x + 0.06, yb_, zz + 0.03, M['breeze'], cn)
                    else:
                        box(x - 0.09, ya_, 0.9, x + 0.09, yb_, h - 0.08, M['brick'], cn)
            # end pier at the water
            box(x - 0.22, sd['y1'] - 0.4, 0, x + 0.22, sd['y1'], h + 0.25, M['brick'], cn)


def fence_span(a, b, y, h, M, cn, breeze=True):
    box(a, y - 0.11, 0, b, y + 0.11, 0.9, M['brick'], cn)
    box(a, y - 0.13, h - 0.08, b, y + 0.13, h, M['stone'], cn)
    n = max(1, int(round((b - a) / 1.6)))
    for i in range(n + 1):
        x = a + (b - a) * i / n
        box(x - 0.18, y - 0.18, 0, x + 0.18, y + 0.18, h + 0.12, M['brick'], cn)
    for i in range(n):
        xa = a + (b - a) * i / n + 0.18
        xb = a + (b - a) * (i + 1) / n - 0.18
        if xb - xa < 0.1:
            continue
        if breeze:
            k = max(1, int((xb - xa) / 0.2))
            for j in range(k + 1):
                xx = xa + (xb - xa) * j / k
                box(xx - 0.03, y - 0.06, 0.9, xx + 0.03, y + 0.06, h - 0.08, M['breeze'], cn)
            for zz in (1.12, 1.36, 1.6):
                box(xa, y - 0.06, zz - 0.03, xb, y + 0.06, zz + 0.03, M['breeze'], cn)
        else:
            box(xa, y - 0.09, 0.9, xb, y + 0.09, h - 0.08, M['brick'], cn)


def build_front_gates(fr, W, M, cn):
    """Front wall with any number of gate openings; all gates stand open so the walkthrough can pass."""
    y, h = fr['y'], fr['height']
    gates = sorted(fr['gates'], key=lambda g: g['x0'])
    cur = 0.0
    for g in gates:
        if g['x0'] - cur > 0.05:
            fence_span(cur, g['x0'], y, h, M, cn, fr.get('breeze_panels', True))
        cur = g['x1']
    if W - cur > 0.05:
        fence_span(cur, W, y, h, M, cn, fr.get('breeze_panels', True))
    for g in gates:
        g0, g1 = g['x0'], g['x1']
        top = h + (0.5 if g['kind'] == 'pedestrian' else 0.25)
        box(g0 - 0.25, y - 0.25, 0, g0, y + 0.25, top, M['brick'], cn)
        box(g1, y - 0.25, 0, g1 + 0.25, y + 0.25, top, M['brick'], cn)
        if g['kind'] == 'vehicle':
            # two leaves folded back inward against the piers
            L = (g1 - g0) / 2
            box(g0 + 0.02, y + 0.12, 0.05, g0 + 0.1, y + 0.12 + L * 0.95, 1.8, M['timber_dk'], cn)
            box(g1 - 0.1, y + 0.12, 0.05, g1 - 0.02, y + 0.12 + L * 0.95, 1.8, M['timber_dk'], cn)
        else:
            box(g0 + 0.02, y + 0.12, 0.05, g0 + 0.1, y + 0.12 + (g1 - g0) * 0.95, 2.0, M['timber_dk'], cn)
            box(g0 - 0.35, y - 0.35, top, g1 + 0.35, y + 0.4, top + 0.12, M['tile_roof'], cn)
            for x in (g0 - 0.125, g1 + 0.125):
                box(x - 0.09, y - 0.32, h - 0.1, x + 0.09, y - 0.25, h + 0.2, M['white'], cn)


def build_neighbours(S, M):
    """Assumed 3-storey neighbours (typical Vietnamese tube houses) built to the property line."""
    cn = 'NEIGHBOURS'
    for nb in S['site'].get('neighbours', []):
        x0, x1, y0, y1, H = nb['x0'], nb['x1'], nb['y0'], nb['y1'], nb['height']
        m = M[nb.get('mat', 'existing')]
        st = nb.get('storeys', 3)
        fh = (H - 1.0) / st
        box(x0, y0 + 1.0, 0, x1, y1, H - 1.0, m, cn)                       # body (front set back 1 m)
        box(x0, y0 + 1.0, H - 1.0, x1, y1, H, m, cn)                       # parapet / roof
        box(x0 + 0.15, y0 + 1.15, H - 0.3, x1 - 0.15, y1 - 0.15, H - 0.05, M['stone_dk'], cn)
        for k in range(st):
            z = k * fh
            if k == 0:   # ground-floor shopfront / garage door
                box(x0 + 0.4, y0 + 0.97, 0.05, x1 - 0.4, y0 + 1.0, 2.9, M['charcoal'], cn)
            else:        # balcony slab + rail + glazed doors on the street face
                box(x0 + 0.1, y0, z - 0.12, x1 - 0.1, y0 + 1.0, z, m, cn)
                box(x0 + 0.1, y0, z, x1 - 0.1, y0 + 0.06, z + 1.0, M['charcoal'], cn)
                box(x0 + 0.6, y0 + 0.97, z + 0.1, x1 - 0.6, y0 + 1.0, z + 2.5, M['glass_dk'], cn)
            box(x0, y0 + 0.9, z + fh - 0.25, x1, y0 + 1.05, z + fh, M['white2'], cn)   # floor band
        # rear (garden) windows
        for k in range(st):
            z = k * fh
            box(x0 + 1.0, y1 - 0.03, z + 1.0, x1 - 1.0, y1 + 0.01, z + 2.4, M['glass_dk'], cn)


# ---------------------------------------------------------------------- site --
def build_site(S, M, trees=True):
    st = S['site']
    W = st['site']['width']
    D = st['site']['depth_west']
    ry = st['river']['bank_y']
    cn = 'SITE'
    box(-60, -12, -0.30, 75, ry - 0.5, -0.02, M['grass'], cn, frame=False)       # surrounding land
    box(0.0, 0.0, -0.06, W, D, 0.0, M['grass'], cn)                                # the plot
    box(-60, -9.5, -0.10, 75, -1.6, 0.0, M['asphalt'], cn, frame=False)          # village road
    box(-60, -1.6, -0.10, 75, 0.0, 0.03, M['paver'], cn, frame=False)            # verge / footpath
    # ONT ground: paved forecourt + service passage gravel + planting beds
    fx0, fy0, fx1, fy1 = S['footprint']
    sp = S['concept'].get('service_passage', [0.0, 1.5])[1]
    box(sp, 0.2, 0.0, W - 0.2, fy0, 0.02, M['paver'], cn)
    box(0.22, 0.2, 0.0, sp, fy1 + 0.4, 0.02, M['paver'] if sp > 2.5 else M['gravel'], cn)
    box(fx1, 0.2, 0.0, W - 0.22, fy1, 0.02, M['gravel'], cn)
    # river and bank
    box(-60, ry - 0.5, -1.2, 75, ry + 0.6, -0.05, M['stone_dk'], cn, frame=False)
    box(-60, ry + 0.6, -0.9, 75, ry + 90, -0.55, M['river'], cn, frame=False)
    # existing north-west building: neutral grey massing (existing condition only)
    nw = st.get('existing_nw_building')
    if nw:
        box(nw['x0'], nw['y0'], 0, nw['x1'], nw['y1'], nw['height'], M['existing'], cn)
        B.gable(nw['x0'], nw['y0'], nw['x1'], nw['y1'], nw['height'], nw['height'] + 1.2,
                M['existing'], cn, axis='y', overhang=0.25)
    if trees:
        C = S['concept']
        for i, (x, y, k) in enumerate(C.get('planting_dnn', []) + C.get('planting_ont', [])):
            if k == 'tree':
                B.tree(x, y, 0.0, 2.2 + (i % 3) * 0.6, M, 'TREES', seed=11 + i)
            elif k in ('palm', 'court'):
                B.tree(x, y, 0.0, 0.9, M, 'TREES', seed=31 + i)
            else:
                B.tree(x, y, -0.6, 0.7, M, 'TREES', seed=51 + i, trunk=False)
        for i, (x, y) in enumerate([(-8, 6), (-14, 22), (-9, 40), (-16, 55), (22, 8), (26, 30), (20, 48), (28, 60)]):
            B.tree(x, y, 0.0, 3.0 + (i % 2), M, 'TREES', seed=71 + i)


# --------------------------------------------------------------------- build --
def build_all(S, massing=False, trees=True):
    sc = B.reset()
    B.COLL.clear()
    B.NOFRAME.clear()
    M = materials(massing)
    for c in ('L0', 'L1', 'GLASS', 'STAIR', 'ROOF', 'PORCH', 'FENCE', 'NEIGHBOURS', 'SITE', 'TREES'):
        coll(c)
    build_house(S, M)
    build_fence(S, M)
    build_neighbours(S, M)
    build_site(S, M, trees=trees)
    B.repair_normals()
    return sc, M


def export_fbx(path):
    """Join per collection+material and export for Unity."""
    import bmesh  # noqa: F401
    for cn, c in list(B.COLL.items()):
        if cn == 'TREES':
            for ob in list(c.objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            continue
        groups = {}
        for ob in list(c.objects):
            if ob.type != 'MESH' or not ob.data.materials:
                continue
            groups.setdefault(ob.data.materials[0].name, []).append(ob)
        for mname, obs in groups.items():
            bpy.ops.object.select_all(action='DESELECT')
            for ob in obs:
                ob.select_set(True)
            bpy.context.view_layer.objects.active = obs[0]
            if len(obs) > 1:
                bpy.ops.object.join()
            j = bpy.context.view_layer.objects.active
            j.name = '%s__%s' % (cn, mname)
            j.data.name = j.name
            # UVs for Unity textures: simple cube projection in world metres
            bpy.ops.object.select_all(action='DESELECT')
            j.select_set(True)
            bpy.context.view_layer.objects.active = j
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.cube_project(cube_size=1.0, scale_to_bounds=False, correct_aspect=False)
            bpy.ops.object.mode_set(mode='OBJECT')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.export_scene.fbx(filepath=path, use_selection=False, object_types={'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                             axis_forward='-Z', axis_up='Y', bake_space_transform=True,
                             mesh_smooth_type='FACE', use_mesh_modifiers=True, add_leaf_bones=False)
    print('FBX_OK', path)


def gpu_setup(sc):
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dev in ('OPTIX', 'CUDA'):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.type == dev for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == dev
                    sc.cycles.device = 'GPU'
                    print('cycles device', dev)
                    return dev
            except Exception:
                continue
    except Exception as e:
        print('gpu setup failed', e)
    return None


def render_views(S, outdir):
    V = S['concept']['viewpoints']
    res = (960, 600) if FAST else (1800, 1125)
    shots = {
        'street': dict(V['street'], lens=24),
        **({'garden': dict(V['garden'], lens=30)} if 'garden' in V else {}),
        'aerial': dict(V['aerial'], lens=35),
        'balcony': dict(V['balcony'], lens=22),
        'riverside': dict(V['riverside'], lens=30),
    }
    shots = {k: v for k, v in shots.items() if True}
    for extra, lens in (('carport', 28), ('atrium', 22)):
        if extra in V:
            shots[extra] = dict(V[extra], lens=lens)
    # pass 1 — clay massing
    sc, M = build_all(S, massing=True, trees=False)
    B.studio_world(sc, 0.34, (0.63, 0.66, 0.72))
    B.set_cycles(sc, samples=16 if FAST else 48)
    gpu_setup(sc)
    sc.view_settings.view_transform = 'AgX'
    B.add_sun(sc, elev=40, rot=230, energy=4.2, angle=1.5)
    sc.render.resolution_x, sc.render.resolution_y = res
    B.cam(sc, (-12.0, -14.0, 20.0), (6.6, 10.0, 3.0), lens=32)
    sc.render.filepath = os.path.join(outdir, 'massing.png')
    bpy.ops.render.render(write_still=True)
    # pass 2 — materials, golden-hour sun from the south-west like the concept image
    sc, M = build_all(S, massing=False, trees=True)
    B.setup_world(sc, strength=0.55)
    B.set_cycles(sc, samples=24 if FAST else 96)
    dev = gpu_setup(sc)
    if dev == 'OPTIX':
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = 'OPTIX'
    sc.cycles.max_bounces = 10
    sc.cycles.diffuse_bounces = 4
    sc.cycles.transparent_max_bounces = 16
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    B.add_sun(sc, elev=24, rot=235, energy=4.6, angle=1.2)
    B.add_sun(sc, elev=55, rot=60, energy=0.5, angle=30)
    # warm interior lamps so windows glow like the concept image
    for lv in S['levels']:
        for nm, x0, y0, x1, y1, k in lv['rooms']:
            if k in ('hab', 'circ', 'spec', 'out') and (x1 - x0) * (y1 - y0) > 4:
                d = bpy.data.lights.new('in', 'POINT')
                d.energy = 120
                d.color = (1.0, 0.78, 0.52)
                d.shadow_soft_size = 0.4
                ob = bpy.data.objects.new('in', d)
                bpy.context.scene.collection.objects.link(ob)
                ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, lv['ztop'] - 0.5)
    # gate lamps
    for x in (5.0, 8.2):
        d = bpy.data.lights.new('lamp', 'POINT')
        d.energy = 25
        d.color = (1.0, 0.7, 0.4)
        ob = bpy.data.objects.new('lamp', d)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = (x, -0.35, 1.95)
    sc.render.resolution_x, sc.render.resolution_y = res
    for nm, v in shots.items():
        B.cam(sc, tuple(v['pos']), tuple(v['look']), lens=v['lens'], clip_start=0.05)
        sc.render.filepath = os.path.join(outdir, nm + '.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', nm)


def main():
    cpath, outdir = argv[0], argv[1]
    S = load(cpath)
    os.makedirs(outdir, exist_ok=True)
    fbx = argv[argv.index('--fbx') + 1] if '--fbx' in argv else None
    if fbx:
        build_all(S, massing=False, trees=False)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(outdir, 'model.blend'))
        export_fbx(fbx)
    if not NO_RENDER:
        render_views(S, outdir)
    print('RENDER_OK')


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    print('RENDER_FAIL')
