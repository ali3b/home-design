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
        for k in ('brick', 'breeze', 'asphalt', 'paver', 'soil', 'existing', 'rail'):
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
            k = max(1, int(round((o1 - o0) / 0.9)))
            for i in range(1, k):
                s = o0 + (o1 - o0) * i / k
                bx(s - 0.03, s + 0.03, sill, head, M['timber_dk'])
            gt = 0.015
            if p['axis'] == 'x':
                box(o0 + fw, c - gt, z0 + sill, o1 - fw, c + gt, z0 + head - fw, M['glass'], 'GLASS')
            else:
                box(c - gt, o0 + fw, z0 + sill, c + gt, o1 - fw, z0 + head - fw, M['glass'], 'GLASS')
        elif kind == 'door':
            bx(o0 - 0.05, o0, 0, head + 0.05, M['timber_dk'])
            bx(o1, o1 + 0.05, 0, head + 0.05, M['timber_dk'])
            bx(o0 - 0.05, o1 + 0.05, head, head + 0.05, M['timber_dk'])
    bx(cur, b, 0, H, m)


# --------------------------------------------------------------------- stair --
def build_stair(st, M):
    cn = 'STAIR'
    x0, y0, x1, y1 = st['x0'], st['y0'], st['x1'], st['y1']
    z0, z1, n = st['z0'], st['z1'], st['risers']
    rise = (z1 - z0) / n
    tread = st['tread']
    half = n // 2
    xm = (x0 + x1) / 2
    run = (half - 1) * tread
    ya = y0 + run                      # top of flight 1 / start of landing
    zl = z0 + half * rise
    # flight 1: west half, going north, solid
    for i in range(half - 1):
        box(x0 + 0.02, y0 + i * tread, z0, xm - 0.02, y0 + (i + 1) * tread, z0 + (i + 1) * rise,
            M['timber'], cn)
    # landing
    box(x0 + 0.02, ya, zl - 0.25, x1 - 0.02, y1 - 0.02, zl, M['timber'], cn)
    # flight 2: east half, from landing going south, floating treads
    for i in range(half - 1):
        zt = zl + (i + 1) * rise
        yb = ya - (i + 1) * tread
        box(xm + 0.02, yb, zt - 0.22, x1 - 0.02, yb + tread, zt, M['timber'], cn)
    # last riser lands on the upper floor at y0 (upper landing room)
    # timber screen between flights (leave the first 0.8 m open as the way in)
    for k in range(int((ya - (y0 + 0.8)) / 0.12) + 1):
        y = y0 + 0.8 + k * 0.12
        if y > ya:
            break
        box(xm - 0.03, y - 0.02, z0, xm + 0.03, y + 0.02, z1, M['timber_dk'], cn)
    # guard on flight 2's west edge over the open first 0.8 m
    for y in (y0 + 0.05, y0 + 0.4, y0 + 0.78):
        zt = zl + (half - 1 - (y - y0) / tread) * rise
        box(xm - 0.03, y - 0.03, zt, xm + 0.03, y + 0.03, z1 + 0.92, M['timber_dk'], cn)
    box(xm - 0.03, y0, z1 + 0.85, xm + 0.03, y0 + 0.8, z1 + 0.92, M['timber_dk'], cn)


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
    ze = max(r['ze'] for r in C['roofs'] if r['x0'] <= fx0 + 0.01)
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
            box(x - 0.12, y + 0.4, z_gf, x + 0.12, y + 0.64, C['roofs'][1]['ze'], M['timber_dk'], 'PORCH')
            box(x - 0.2, y + 0.32, z_gf, x + 0.2, y + 0.72, z_gf + 0.3, M['stone'], 'PORCH')
    if C.get('stair'):
        build_stair(C['stair'], M)


# --------------------------------------------------------------------- fence --
def build_fence(S, M):
    C, W = S['concept'], S['site']['site']['width']
    f = C.get('fence', {})
    cn = 'FENCE'
    fr = f.get('front')
    if fr:
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
        y0 = fr['y'] if fr else 0.0
        for x in (0.11, W - 0.11):
            box(x - 0.11, y0, 0, x + 0.11, sd['y1'], sd['height'], M['brick'], cn)
            box(x - 0.13, y0, sd['height'], x + 0.13, sd['y1'], sd['height'] + 0.08, M['stone'], cn)


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
    box(1.5, 0.2, 0.0, W - 0.2, fy0, 0.02, M['paver'], cn)
    box(0.22, 0.2, 0.0, 1.5, fy1 + 0.4, 0.02, M['gravel'], cn)
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
    for c in ('L0', 'L1', 'GLASS', 'STAIR', 'ROOF', 'PORCH', 'FENCE', 'SITE', 'TREES'):
        coll(c)
    build_house(S, M)
    build_fence(S, M)
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
        'garden': dict(V['garden'], lens=30),
        'aerial': dict(V['aerial'], lens=35),
        'balcony': dict(V['balcony'], lens=22),
    }
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
