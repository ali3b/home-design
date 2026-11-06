"""Blender-side builder + renderer.  Run inside Blender:
    blender -b --factory-startup --python lib/bbuild.py -- <scheme_key> <outdir>

Builds one model from a scheme module and emits:
    plan_<i>.png    top orthographic Freestyle line plan, per level
    roof.png        top ortho Freestyle with roof planes shown
    site.png        top ortho Freestyle of the site works only
    section.png     clipped ortho Freestyle long section
    massing.png     white model, 3/4 aerial
    material.png    full palette, garden eye level
Everything derives from one geometry set, so drawings and renders cannot disagree.
"""
import bpy, bmesh, math, sys, os, json
from mathutils import Vector
from .rectwalls import derive, consolidate

# ------------------------------------------------------------------ setup ---
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.render.resolution_percentage = 100
    return sc


COLL = {}


def coll(name):
    if name in COLL:
        return COLL[name]
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    COLL[name] = c
    return c


def link(ob, cname):
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll(cname).objects.link(ob)


# ----------------------------------------------------------------- materials -
def mat(name, color, rough=0.85, metal=0.0, spec=0.4, tex=None, texscale=1.0,
        emit=None, transmission=0.0, ior=1.45, alpha=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = spec
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = spec
    if transmission:
        bsdf.inputs['Transmission Weight'].default_value = transmission \
            if 'Transmission Weight' in bsdf.inputs else 0
        bsdf.inputs['IOR'].default_value = ior
    if alpha < 1.0:
        bsdf.inputs['Alpha'].default_value = alpha
        m.blend_method = 'BLEND' if hasattr(m, 'blend_method') else None
    if tex:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (texscale, texscale, texscale)
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        if tex == 'wave':
            t = nt.nodes.new('ShaderNodeTexWave')
            t.wave_type = 'BANDS'
            t.bands_direction = 'X'
            t.inputs['Scale'].default_value = 1.0
            t.inputs['Distortion'].default_value = 1.2
            t.inputs['Detail'].default_value = 2.0
            nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
            src = t.outputs['Fac']
        elif tex == 'brick':
            t = nt.nodes.new('ShaderNodeTexBrick')
            t.inputs['Scale'].default_value = 1.0
            t.inputs['Mortar Size'].default_value = 0.012
            t.inputs['Brick Width'].default_value = 0.22
            t.inputs['Row Height'].default_value = 0.30
            t.inputs['Color1'].default_value = (*color, 1)
            t.inputs['Color2'].default_value = (*(c * 1.12 for c in color), 1)
            t.inputs['Mortar'].default_value = (*(c * 0.72 for c in color), 1)
            nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
            src = t.outputs['Color']
        elif tex == 'noise':
            t = nt.nodes.new('ShaderNodeTexNoise')
            t.inputs['Scale'].default_value = 6.0
            t.inputs['Detail'].default_value = 6.0
            nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
            src = t.outputs['Fac']
        else:
            src = None
        if src is not None and tex in ('wave', 'noise'):
            # never drive Base Color straight from a greyscale factor -- tint it
            mix = nt.nodes.new('ShaderNodeMixRGB')
            mix.blend_type = 'MIX'
            mix.inputs['Fac'].default_value = 0.30 if tex == 'noise' else 0.22
            mix.inputs['Color1'].default_value = (*color, 1)
            mix.inputs['Color2'].default_value = (
                *(min(1.0, c * 1.35 + 0.02) for c in color), 1)
            nt.links.new(src, mix.inputs['Fac'])
            nt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
            src = mix.outputs['Color']
        elif src is not None:
            nt.links.new(src, bsdf.inputs['Base Color'])
        bump = nt.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = 0.35 if tex in ('wave', 'brick') else 0.10
        if tex in ('wave', 'brick', 'noise'):
            nt.links.new(src, bump.inputs['Height'])
            nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


MASS_PAL = {
    'plaster': (0.815, 0.805, 0.785), 'plaster_w': (0.850, 0.845, 0.835),
    'tile_roof': (0.150, 0.155, 0.163), 'timber': (0.300, 0.240, 0.190),
    'timber_dk': (0.235, 0.185, 0.145), 'slat': (0.335, 0.270, 0.210),
    'terracotta': (0.640, 0.490, 0.395), 'cement_tile': (0.700, 0.675, 0.620),
    'stone': (0.645, 0.640, 0.625), 'stone_dk': (0.470, 0.465, 0.450),
    'glass': (0.200, 0.240, 0.265), 'glass_dk': (0.200, 0.240, 0.265),
    'water': (0.290, 0.470, 0.510), 'river': (0.290, 0.470, 0.510),
    'grass': (0.545, 0.585, 0.475), 'gravel': (0.620, 0.610, 0.580),
    'leaf': (0.375, 0.455, 0.315), 'leaf2': (0.425, 0.500, 0.355),
    'dark': (0.175, 0.175, 0.175), 'charcoal': (0.175, 0.175, 0.175),
    'pv': (0.170, 0.195, 0.235), 'brick_red': (0.515, 0.330, 0.265),
    'white': (0.815, 0.805, 0.785), 'white2': (0.815, 0.805, 0.785),
}


def interior_lights(S, energy=42.0):
    """Fill inside habitable rooms.

    Concept renders have no ceiling voids and no daylight modelling, so any
    surface that only sees the sky through alpha-blended glass comes back
    black.  A lamp per room keeps interiors legible without touching the
    exterior, which is still sun- and sky-lit.
    """
    kind_of = S.get('kind_of', {})
    n = 0
    for lv in S['levels']:
        seen = set()
        for nm, x0, y0, x1, y1, kind in lv['rooms']:
            if kind not in ('hab', 'spec', 'circ') or nm in seen:
                continue
            if (x1 - x0) * (y1 - y0) < 4.0:
                continue
            seen.add(nm)
            d = bpy.data.lights.new('in', 'POINT')
            d.energy = energy
            d.shadow_soft_size = 1.1
            d.color = (1.0, 0.94, 0.84)
            ob = bpy.data.objects.new('in', d)
            bpy.context.scene.collection.objects.link(ob)
            ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, lv['z'] + 1.85)
            n += 1
    return n


def reveal_fill(S, energy=18.0):
    """Soft downward fill for window/door reveals and deep soffits.

    `consolidate()` leaves genuine 0.30 m reveals, and a reveal only sees sky
    through its own opening, so it renders near-black even on a bright day.
    These are lamps placed just outside each opening on the sunward side.
    """
    n = 0
    for lv in S['levels']:
        z0, z1 = lv['z'], lv['ztop']
        for w in consolidate(derive(lv['rooms'], S['footprint'],
                                    lv.get('doors', []), S['kind_of'])):
            for o0, o1, sill, head, *_ in w['openings']:
                if head - sill < 0.8:
                    continue
                mid = (o0 + o1) / 2
                zc = z0 + (sill + head) / 2
                if w['axis'] == 'x':          # wall() runs in Y at x=coord
                    loc = Vector((w['coord'], mid, zc))
                    nrm = Vector((1.0, 0.0, 0.0))
                    along = Vector((0.0, 1.0, 0.0))
                else:
                    loc = Vector((mid, w['coord'], zc))
                    nrm = Vector((0.0, 1.0, 0.0))
                    along = Vector((1.0, 0.0, 0.0))
                for s in (-1.0, 1.0):
                    p = loc + along * (s * (o1 - o0) * 0.32) + nrm * 0.55
                    d = bpy.data.lights.new('rf', 'AREA')
                    d.shape = 'RECTANGLE'
                    d.size = max(0.5, (o1 - o0) * 0.5)
                    d.size_y = max(0.4, head - sill)
                    d.energy = energy
                    d.color = (0.92, 0.95, 1.0)
                    ob = bpy.data.objects.new('rf', d)
                    bpy.context.scene.collection.objects.link(ob)
                    ob.location = p
                    ob.rotation_euler = (-nrm).to_track_quat('-Z', 'Y').to_euler()
                    n += 1
    return n


def build_materials(massing=False):
    M = {}
    if massing:
        # clay study model: white plaster volumes, mid-grey roofs, glazing read
        # as darker recesses.  Principled (not emission) so the massing has
        # real light and shade instead of a flat silhouette.
        pal = {
            'plaster': (0.880, 0.872, 0.858), 'plaster_s': (0.700, 0.694, 0.684),
            'plaster_w': (0.930, 0.926, 0.918),
            'white': (0.905, 0.900, 0.890), 'white2': (0.845, 0.840, 0.830),
            'tile_roof': (0.300, 0.302, 0.312), 'timber': (0.560, 0.520, 0.470),
            'timber_dk': (0.480, 0.442, 0.396), 'slat': (0.560, 0.520, 0.470),
            'terracotta': (0.780, 0.740, 0.700), 'cement_tile': (0.800, 0.792, 0.775),
            'stone': (0.740, 0.735, 0.722), 'stone_dk': (0.600, 0.596, 0.586),
            'glass': (0.470, 0.545, 0.585), 'glass_dk': (0.420, 0.490, 0.535),
            'water': (0.560, 0.660, 0.690), 'river': (0.600, 0.680, 0.700),
            'grass': (0.720, 0.742, 0.660), 'gravel': (0.745, 0.735, 0.712),
            'leaf': (0.660, 0.700, 0.620), 'leaf2': (0.685, 0.722, 0.640),
            'dark': (0.330, 0.330, 0.330), 'charcoal': (0.330, 0.330, 0.330),
            'pv': (0.300, 0.315, 0.335), 'brick_red': (0.720, 0.680, 0.645),
        }
        for nm, col in pal.items():
            m = bpy.data.materials.new('M_' + nm)
            m.use_nodes = True
            b = m.node_tree.nodes['Principled BSDF']
            b.inputs['Base Color'].default_value = (*col, 1)
            b.inputs['Roughness'].default_value = 0.72
            if 'Specular IOR Level' in b.inputs:
                b.inputs['Specular IOR Level'].default_value = 0.25
            M[nm] = m
        return M
    M['plaster'] = mat('plaster', (0.760, 0.722, 0.655), 0.95, tex='noise', texscale=0.6)
    M['plaster_s'] = mat('plaster_s', (0.545, 0.530, 0.505), 0.92,
                         tex='noise', texscale=1.1)
    M['plaster_w'] = mat('plaster_w', (0.93, 0.915, 0.88), 0.92)
    M['tile_roof'] = mat('tile_roof', (0.215, 0.098, 0.066), 0.86, tex='brick', texscale=1.0)
    M['timber'] = mat('timber', (0.232, 0.140, 0.085), 0.82, tex='wave', texscale=1.0)
    M['timber_dk'] = mat('timber_dk', (0.128, 0.083, 0.052), 0.80, tex='wave', texscale=1.2)
    M['slat'] = mat('slat', (0.318, 0.205, 0.115), 0.84, tex='wave', texscale=1.0)
    M['terracotta'] = mat('terracotta', (0.545, 0.290, 0.170), 0.80, tex='brick', texscale=1.0)
    M['cement_tile'] = mat('cement_tile', (0.760, 0.700, 0.590), 0.78, tex='brick', texscale=1.0)
    M['stone'] = mat('stone', (0.605, 0.580, 0.520), 0.88, tex='noise', texscale=1.2)
    M['stone_dk'] = mat('stone_dk', (0.430, 0.405, 0.370), 0.90)
    # Architectural glazing: alpha-blended tint rather than transmission.
    # Glazing: a dark, glossy, largely transparent sheet.  Alpha rather than
    # transmission -- transmission is noisy at concept sample counts and, with
    # unlit interiors behind it, collapses to black.  Kept light enough in tone
    # that a window never reads as a hole in the elevation.
    M['glass'] = mat('glass', (0.62, 0.70, 0.74), 0.045, spec=1.0, alpha=0.16)
    M['glass_dk'] = mat('glass_dk', (0.50, 0.58, 0.63), 0.055, spec=1.0,
                        alpha=0.30)
    M['water'] = mat('water', (0.115, 0.400, 0.430), 0.06, spec=1.0, transmission=0.55, ior=1.33)
    M['river'] = mat('river', (0.300, 0.395, 0.410), 0.18, spec=0.6)
    M['grass'] = mat('grass', (0.315, 0.415, 0.185), 0.95, tex='noise', texscale=0.5)
    M['gravel'] = mat('gravel', (0.560, 0.530, 0.460), 0.95, tex='noise', texscale=2.0)
    M['leaf'] = mat('leaf', (0.205, 0.330, 0.135), 0.92, tex='noise', texscale=1.6)
    M['leaf2'] = mat('leaf2', (0.255, 0.375, 0.155), 0.92, tex='noise', texscale=1.4)
    M['dark'] = mat('dark', (0.075, 0.070, 0.062), 0.90)
    M['charcoal'] = mat('charcoal', (0.115, 0.110, 0.100), 0.85)
    M['white'] = mat('white', (0.90, 0.895, 0.885), 0.65)
    M['white2'] = mat('white2', (0.82, 0.815, 0.805), 0.70)
    M['pv'] = mat('pv', (0.035, 0.040, 0.055), 0.22, spec=0.9)
    M['brick_red'] = mat('brick_red', (0.420, 0.215, 0.140), 0.88, tex='brick', texscale=1.0)
    return M


# ---------------------------------------------------------------- geometry --
NOFRAME = set()


def box(x0, y0, z0, x1, y1, z1, m, cname, bevel=0.0, frame=True):
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if z1 < z0:
        z0, z1 = z1, z0
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    if dx <= 0 or dy <= 0 or dz <= 0:
        return None
    me = bpy.data.meshes.new('m')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('m', me)
    ob.scale = (dx, dy, dz)
    ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    link(ob, cname)
    ob.data.materials.append(m)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.select_set(False)
    if bevel:
        b = ob.modifiers.new('bev', 'BEVEL')
        b.width = bevel
        b.segments = 2
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=b.name)
    if not frame:
        NOFRAME.add(ob.name)
    return ob


def prism(points_xy, z0, z1, m, cname):
    """Extrude a polygon between two z heights."""
    me = bpy.data.meshes.new('m')
    bm = bmesh.new()
    vs = [bm.verts.new((p[0], p[1], z0)) for p in points_xy]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    verts = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=(0, 0, z1 - z0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('m', me)
    link(ob, cname)
    ob.data.materials.append(m)
    return ob


def _plate(vv, thick, m, cname):
    me = bpy.data.meshes.new('m')
    bm = bmesh.new()
    bv = [bm.verts.new(p) for p in vv]
    bm.faces.new(bv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=-thick)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('m', me)
    link(ob, cname)
    ob.data.materials.append(m)
    return ob


def gable(x0, y0, x1, y1, ze, zr, m, cname, axis='x', overhang=0.0, thick=0.14):
    """Two sloping planes + two gable triangles.
    axis='x' -> ridge runs along X (gable ends face north/south)."""
    ox0, oy0, ox1, oy1 = x0 - overhang, y0 - overhang, x1 + overhang, y1 + overhang
    if axis == 'x':
        ym = (oy0 + oy1) / 2
        _plate([(ox0, oy0, ze), (ox1, oy0, ze), (ox1, ym, zr), (ox0, ym, zr)],
               thick, m, cname)
        _plate([(ox0, ym, zr), (ox1, ym, zr), (ox1, oy1, ze), (ox0, oy1, ze)],
               thick, m, cname)
        _plate([(ox0, oy0, ze), (ox1, oy0, ze), (ox1, ym, zr)], 0.10, m, cname)
        _plate([(ox0, oy1, ze), (ox0, ym, zr), (ox1, ym, zr)], 0.10, m, cname)
    else:
        xm = (ox0 + ox1) / 2
        _plate([(ox0, oy0, ze), (ox0, oy1, ze), (xm, oy1, zr), (xm, oy0, zr)],
               thick, m, cname)
        _plate([(xm, oy0, zr), (xm, oy1, zr), (ox1, oy1, ze), (ox1, oy0, ze)],
               thick, m, cname)
        _plate([(ox0, oy0, ze), (xm, oy0, zr), (ox1, oy0, ze)], 0.10, m, cname)
        _plate([(ox0, oy1, ze), (xm, oy1, zr), (ox1, oy1, ze)], 0.10, m, cname)


def hip(x0, y0, x1, y1, ze, zr, m, cname, ridge_frac=None, overhang=0.0, thick=0.14):
    """Hip roof.  The ridge runs parallel to the roof's longer side, and its
    length is whatever the short side leaves over — the same rule the drawing
    engine uses in lib/sheetgen.py, so the roof plan and the render cannot
    disagree.  Pass ridge_frac only to draw something deliberately different.
    """
    ox0, oy0, ox1, oy1 = x0 - overhang, y0 - overhang, x1 + overhang, y1 + overhang
    dx, dy = ox1 - ox0, oy1 - oy0
    along_y = dy >= dx
    if ridge_frac is None:
        long_, short_ = (dy, dx) if along_y else (dx, dy)
        ridge_frac = max(0.0, min(0.95, (long_ - short_) / long_))
    # Build in a frame whose ridge runs along +x, then transpose if needed.
    if along_y:
        rx0, ry0, rx1, ry1 = oy0, ox0, oy1, ox1
    else:
        rx0, ry0, rx1, ry1 = ox0, oy0, ox1, oy1
    h = ry1 - ry0
    a0 = ry0 + h * (1 - ridge_frac) / 2
    a1 = ry1 - h * (1 - ridge_frac) / 2
    faces = [
        [(rx0, ry0, ze), (rx1, ry0, ze), (rx1, a0, zr), (rx0, a0, zr)],
        [(rx0, a0, zr), (rx1, a0, zr), (rx1, a1, zr), (rx0, a1, zr)],
        [(rx0, a1, zr), (rx1, a1, zr), (rx1, ry1, ze), (rx0, ry1, ze)],
        [(rx0, ry0, ze), (rx0, a0, zr), (rx0, a1, zr), (rx0, ry1, ze)],
        [(rx1, ry0, ze), (rx1, a0, zr), (rx1, a1, zr), (rx1, ry1, ze)],
    ]
    if along_y:
        faces = [[(y, x, z) for x, y, z in f] for f in faces]
    for vv in faces:
        me = bpy.data.meshes.new('m')
        bm = bmesh.new()
        bv = [bm.verts.new(p) for p in vv]
        bm.faces.new(bv)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=-thick)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new('m', me)
        link(ob, cname)
        ob.data.materials.append(m)


# ------------------------------------------------------------------- walls --
def wall(axis, fixed, t0, t1, z0, z1, thick, m, cname, openings=(), m_glass=None):
    """axis 'x': runs in Y from t0..t1 at x=fixed. axis 'y': runs in X.
    openings: (s0, s1, sill, head, kind) in the running direction."""
    ops = sorted([o for o in openings if o[0] < t1 and o[1] > t0])
    segs = []
    cur = t0
    for a, b, sill, head, kind in ops:
        a = max(a, t0)
        b = min(b, t1)
        if a > cur:
            segs.append((cur, a, z0, z1, m))
        if sill > z0 + 0.001:
            segs.append((a, b, z0, min(sill, z1), m))
        if head < z1 - 0.001:
            segs.append((a, b, max(head, z0), z1, m))
        cur = b
    if cur < t1:
        segs.append((cur, t1, z0, z1, m))
    out = []
    for a, b, c, d, mm in segs:
        if axis == 'x':
            out.append(box(fixed - thick / 2, a, c, fixed + thick / 2, b, d, mm, cname))
        else:
            out.append(box(a, fixed - thick / 2, c, b, fixed + thick / 2, d, mm, cname))
    if m_glass is not None:
        for a, b, sill, head, kind in ops:
            a = max(a, t0)
            b = min(b, t1)
            # sill/head are storey-relative; z0/z1 are absolute
            if head - sill > 0.2:
                zs, zh = z0 + sill, z0 + head
                zs, zh = min(zs, z1), min(zh, z1)
                if zh <= zs:
                    continue
                if axis == 'x':
                    out.append(box(fixed - 0.03, a + 0.04, zs,
                                   fixed + 0.03, b - 0.04, zh, m_glass, cname))
                else:
                    out.append(box(a + 0.04, fixed - 0.03, zs,
                                   b - 0.04, fixed + 0.03, zh, m_glass, cname))
    return [o for o in out if o]

# ------------------------------------------------------------------ scenery --
def tree(x, y, z, r, M, cname='SITE', seed=1, trunk=True):
    if trunk:
        box(x - 0.13, y - 0.13, z, x + 0.13, y + 0.13, z + r * 1.15,
            M['timber_dk'], cname)
    rng = __import__('random')
    rng.seed(seed)
    for i in range(4):
        a = rng.uniform(0, 6.28)
        d = rng.uniform(0, r * 0.42)
        rr = r * rng.uniform(0.62, 1.0)
        me = bpy.data.meshes.new('m')
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        for v in bm.verts:
            v.co *= 1.0 + rng.uniform(-0.17, 0.17)
            v.co.x *= 1.02
            v.co.y *= 1.02
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new('m', me)
        ob.location = (x + math.cos(a) * d, y + math.sin(a) * d,
                       z + r * 1.45 + rng.uniform(-0.2, 0.35) * r)
        ob.scale = (rr, rr, rr * 0.88)
        link(ob, cname)
        ob.data.materials.append(M['leaf'] if i % 2 == 0 else M['leaf2'])


def build_site(S, M, cname='SITE'):
    # big context planes: visible, but never allowed to drive camera framing
    box(-40, -30, -0.55, 60, 96, -0.30, M['grass'], cname, frame=False)   # field
    # distant tree line so the horizon is not a bare edge
    for tx, ty, tr, sd in ((-16.0, 4.0, 4.2, 11), (-24.0, 16.0, 5.0, 12),
                           (-13.0, 30.0, 4.6, 13), (-22.0, 42.0, 5.4, 14),
                           (-15.5, 54.0, 4.4, 15), (-25.0, 62.0, 5.2, 16),
                           (-12.0, 68.0, 4.8, 17), (-31.0, 26.0, 5.6, 18),
                           (-34.0, 48.0, 5.0, 19), (-28.0, 68.0, 4.6, 20),
                           (17.0, 74.0, 4.2, 21), (-30.0, 8.0, 5.8, 22)):
        tree(tx, ty, 0.0, tr, M, cname, seed=sd)
    box(-0.2, -0.2, -0.30, 13.7, 65.2, -0.06, M['grass'], cname)          # lawn
    box(11.30, -0.2, -0.24, 13.50, 65.2, 0.02, M['gravel'], cname)       # service lane
    box(-8, 65.0, -0.55, 40, 82, -0.34, M['river'], cname, frame=False)  # river
    box(-8, 63.2, -0.34, 40, 65.0, -0.20, M['stone'], cname, frame=False)  # edge
    # boundary fence: posts + rail, both sides + river end
    for xx in (0.0, 13.5):
        for y in range(0, 66, 3):
            box(xx - 0.07, y - 0.07, 0, xx + 0.07, y + 0.07, 1.55,
                M['timber_dk'], cname)
        box(xx - 0.04, 0, 1.35, xx + 0.04, 65, 1.45, M['timber_dk'], cname)
        box(xx - 0.04, 0, 0.75, xx + 0.04, 65, 0.85, M['timber_dk'], cname)
    for xx in range(-6, 34, 3):
        box(xx - 0.07, 63.2 - 0.07, 0, xx + 0.07, 63.2 + 0.07, 1.55,
            M['timber_dk'], cname)
    box(-6, 63.16, 1.35, 34, 63.24, 1.45, M['timber_dk'], cname)
    # existing koi pond (assumed size, from the annotated aerial)
    px0, py0, px1, py1 = S['pond']
    box(px0 - 0.30, py0 - 0.30, -0.30, px0 + 0.02, py1 + 0.30, 0.32,
        M['stone_dk'], cname)
    box(px1 - 0.02, py0 - 0.30, -0.30, px1 + 0.30, py1 + 0.30, 0.32,
        M['stone_dk'], cname)
    box(px0 - 0.30, py0 - 0.30, -0.30, px1 + 0.30, py0 + 0.02, 0.32,
        M['stone_dk'], cname)
    box(px0 - 0.30, py1 - 0.02, -0.30, px1 + 0.30, py1 + 0.30, 0.32,
        M['stone_dk'], cname)
    box(px0, py0, -0.06, px1, py1, 0.30, M['water'], cname)
    # existing riverside cottage (renovate, not enlarge)
    cx0, cy0, cx1, cy1 = S['cottage']
    box(cx0, cy0, 0.0, cx1, cy1, 2.85, M['brick_red'], cname)
    gable(cx0, cy0, cx1, cy1, 2.85, 4.35, M['tile_roof'], cname, axis='x',
          overhang=0.45)
    # phase-2 pool + pool house + braai
    ax0, ay0, ax1, ay1 = S['pool']
    box(ax0 - 0.35, ay0 - 0.35, -0.30, ax1 + 0.35, ay1 + 0.35, 0.12,
        M['terracotta'], cname)
    box(ax0, ay0, -1.30, ax1, ay1, -1.18, M['plaster_w'], cname)
    box(ax0, ay0, -0.12, ax1, ay1, 0.02, M['water'], cname)
    bx0, by0, bx1, by1 = S['poolhouse']
    box(bx0, by0, 0.0, bx1, by0 + 0.16, 2.95, M['plaster'], cname)
    box(bx0, by1 - 0.16, 0.0, bx1, by1, 2.95, M['plaster'], cname)
    box(bx1 - 0.16, by0, 0.0, bx1, by1, 2.95, M['plaster'], cname)
    box(bx0, by0, 0.0, bx1, by1, 0.06, M['cement_tile'], cname)
    hip(bx0, by0, bx1, by1, 2.95, 4.25, M['tile_roof'], cname, overhang=0.7)
    cx0, cy0, cx1, cy1 = S['braai']
    box(cx0, cy0, 0.0, cx1, cy1, 0.92, M['brick_red'], cname)
    box(cx0 - 0.12, cy0 - 0.12, 0.92, cx1 + 0.12, cy1 + 0.12, 1.06,
        M['stone'], cname)
    for i, (tx, ty) in enumerate(S.get('trees', [])):
        tree(tx, ty, -0.04, 2.3 + (i % 3) * 0.75, M, seed=17 + i)


# ------------------------------------------------------------------- render --
def studio_world(sc, strength=1.0, color=(0.90, 0.91, 0.93)):
    w = bpy.data.worlds.new('w')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (*color, 1)
    bg.inputs['Strength'].default_value = strength
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    return w


def setup_world(sc, sun_elev=48.0, sun_rot=118.0, strength=1.0):
    """A bright vertical-gradient sky.

    The Nishita sky model renders almost black at the zenith once AgX and a low
    world strength are applied, which showed up as a hard black band across the
    top of every aerial.  A three-stop ramp off the view vector's Z is duller but
    predictable, and it keeps the shaded sides of the building readable.
    """
    w = bpy.data.worlds.new('w')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    rng = nt.nodes.new('ShaderNodeMapRange')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    rng.inputs['From Min'].default_value = -0.25
    rng.inputs['From Max'].default_value = 0.75
    rng.clamp = True
    els = ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (0.52, 0.52, 0.49, 1.0)          # below the horizon
    els[1].position = 0.30
    els[1].color = (0.84, 0.82, 0.76, 1.0)          # hazy horizon
    e2 = els.new(0.62)
    e2.color = (0.62, 0.70, 0.82, 1.0)             # mid sky
    e3 = els.new(1.0)
    e3.color = (0.42, 0.55, 0.76, 1.0)             # zenith
    nt.links.new(geo.outputs['Incoming'], sep.inputs['Vector'])
    nt.links.new(sep.outputs['Z'], rng.inputs['Value'])
    nt.links.new(rng.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])


def add_sun(sc, elev=48.0, rot=118.0, energy=3.4, angle=1.4):
    d = bpy.data.lights.new('sun', 'SUN')
    d.energy = energy
    d.angle = math.radians(angle)
    ob = bpy.data.objects.new('sun', d)
    bpy.context.scene.collection.objects.link(ob)
    e, r = math.radians(elev), math.radians(rot)
    dvec = Vector((math.cos(e) * math.cos(r), math.cos(e) * math.sin(r), math.sin(e)))
    ob.location = dvec * 40
    ob.rotation_euler = dvec.to_track_quat('Z', 'Y').to_euler()
    return ob


def cam(sc, loc, target, lens=35.0, ortho=None, clip_start=None):
    cd = bpy.data.cameras.new('c')
    ob = bpy.data.objects.new('c', cd)
    sc.collection.objects.link(ob)
    if ortho:
        cd.type = 'ORTHO'
        cd.ortho_scale = ortho
    else:
        cd.lens = lens
        cd.sensor_width = 36.0
    if clip_start is not None:
        cd.clip_start = clip_start
    cd.clip_end = 900
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = ob
    return ob


def freestyle(sc, thickness=1.5, crease=1.35, color=(0.10, 0.09, 0.08),
               hidden=True, silhouette=True, border=True, crease_on=True,
               contour=True, external=True):
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = 'ABSOLUTE'
    sc.render.line_thickness = thickness
    vl = bpy.context.view_layer
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = 'EDITOR'
    fs.crease_angle = crease
    ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new('plan')
    ls.select_by_edge_types = True
    ls.select_silhouette = silhouette
    ls.select_border = border
    ls.select_crease = crease_on
    ls.select_contour = contour
    ls.select_external_contour = external
    ls.select_edge_mark = True
    ls.select_material_boundary = True
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new('L')
    ls.linestyle.color = color
    ls.linestyle.thickness = thickness
    ls.linestyle.alpha = 1.0
    if hidden:
        ls.select_by_visibility = True
        ls.visibility = 'VISIBLE'
    return ls


def show_only(names, hide=()):
    for cn, c in COLL.items():
        for ob in c.objects:
            ob.hide_render = (cn not in names)


def set_cycles(sc, samples=110, res=None, thresh=0.02, transparent=False):
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = thresh
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.transmission_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    if res is not None:
        sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'


# ------------------------------------------------------------------ normals ---
def repair_normals(names=None):
    """Point every face outwards.  gable()/hip() build raw bmesh geometry."""
    fixed = 0
    for cn, c in COLL.items():
        if names and cn not in names:
            continue
        for ob in c.objects:
            if ob.type != 'MESH' or not ob.data.polygons:
                continue
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            before = [f.normal.copy() for f in bm.faces]
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            after = [f.normal.copy() for f in bm.faces]
            if any(a.dot(b) < 0 for a, b in zip(before, after)):
                bm.to_mesh(ob.data)
                ob.data.update()
                fixed += 1
            bm.free()
    return fixed


def door_spec(rooms, doors):
    """Resolve named door anchors to axis/coord/pos from the room set."""
    out = []
    for a, b, kind in doors:
        out.append((a, b, kind))
    return out


# -------------------------------------------------------------------- main ---
def build_scheme(S, M, cname_prefix=''):
    """Create collections/geometry. Returns dict of useful extents."""
    fp = S['footprint']
    lvl_objs = []
    for i, lv in enumerate(S['levels']):
        cn = f'L{i}'
        coll(cn)
        z0, z1 = lv['z'], lv['ztop']
        rs = lv['rooms']
        # floor slab
        box(fp[0] - 0.16, fp[1] - 0.16, z0 - 0.22, fp[2] + 0.16, fp[3] + 0.16, z0,
            M[lv.get('floor', 'cement_tile')], cn)
        # optional cantilever / balcony slabs outside the footprint
        for ex in lv.get('slab_extra', ()):
            box(ex[0], ex[1], z0 - 0.22, ex[2], ex[3], z0,
                M[lv.get('floor', 'cement_tile')], cn)
        # walls: external envelope in plaster, wet/service in a darker screed
        for w in consolidate(derive(rs, fp, lv.get('doors', []), S['kind_of'])):
            kinds = [S['kind_of'].get(n, 'hab') for n in w['rooms']]
            if all(k == 'out' for k in kinds):
                m = M['glass']
            elif all(k == 'plant' for k in kinds):
                m = M['glass']
            elif 'serv' in kinds and w.get('ext'):
                m = M['plaster_s']
            else:
                m = M['plaster']
            # derive() reports axis as the direction the wall RUNS, so a wall
            # listed as axis 'x' sits at a constant y.  wall() wants the axis
            # its `coord` belongs to, hence the swap.
            waxis = 'x' if w['axis'] == 'y' else 'y'
            wall(waxis, w['coord'], w['t0'], w['t1'], z0, z1, w['thick'],
                 m, cn, w['openings'], M['glass'])
        # Ceiling / soffit at the top of the level.  Drawn per room, skipping
        # anything outdoors or a void, so the rain-garden slot, the light court
        # and the internal lane stay open to the sky — which is the whole idea of
        # three of these options.
        if lv.get('ceiling') is not False:
            cz = lv.get('ztop', z1)
            for r in rs:
                k = S['kind_of'].get(r[0], 'hab')
                if k in ('out', 'plant', 'water') or r[0] in ('void', 'lane'):
                    continue
                box(r[1], r[2], cz - 0.14, r[3], r[4], cz, M['plaster'], cn)
        lvl_objs.append(cn)
    # roofs
    coll('ROOF')
    MS = S['massing']
    for r in MS.get('roofs', []):
        k = r.get('kind', 'gable')
        if k == 'gable':
            gable(r['x0'], r['y0'], r['x1'], r['y1'], r['ze'], r['zr'],
                  M[r.get('mat', 'tile_roof')], 'ROOF',
                  axis=r.get('axis', 'x'), overhang=r.get('overhang', 0.9))
        elif k == 'hip':
            hip(r['x0'], r['y0'], r['x1'], r['y1'], r['ze'], r['zr'],
                M[r.get('mat', 'tile_roof')], 'ROOF',
                ridge_frac=r.get('ridge_frac'),
                overhang=r.get('overhang', 0.9))
        elif k == 'flat':
            box(r['x0'], r['y0'], r['ze'], r['x1'], r['y1'], r['ze'] + 0.30,
                M[r.get('mat', 'cement_tile')], 'ROOF')
    # Close the band between the top of the walls and the eaves.  With deep
    # overhangs the roof sits above the wall head, and without this the gap
    # renders as a dark slot running right round the building.
    top_z = S['levels'][-1]['ztop'] if S.get('levels') else 0.0
    for r in MS.get('roofs', []):
        if r.get('ze', 0.0) > top_z + 0.05:
            box(r['x0'] - 0.15, r['y0'] - 0.15, top_z - 0.02,
                r['x1'] + 0.15, r['y1'] + 0.15, r['ze'] - 0.28, M['plaster'], 'ROOF')
    # eaves fascia + soffit band (perimeter beams only, never a slab)
    for r in MS.get('fascia', []):
        x0, y0, x1, y1, ze = r['x0'], r['y0'], r['x1'], r['y1'], r['ze']
        t = 0.16
        box(x0, y0, ze - 0.30, x1, y0 + t, ze, M['timber_dk'], 'ROOF')
        box(x0, y1 - t, ze - 0.30, x1, y1, ze, M['timber_dk'], 'ROOF')
        box(x0, y0, ze - 0.30, x0 + t, y1, ze, M['timber_dk'], 'ROOF')
        box(x1 - t, y0, ze - 0.30, x1, y1, ze, M['timber_dk'], 'ROOF')
    build_site(S['site'], M, 'SITE')
    repair_normals()
    return True


def bbox(names):
    xs, ys, zs = [], [], []
    for cn in names:
        for ob in COLL.get(cn, []).objects if hasattr(COLL.get(cn, []), 'objects') else []:
            pass
    for cn in names:
        c = COLL.get(cn)
        if not c:
            continue
        for ob in c.objects:
            if ob.hide_render or ob.name in NOFRAME:
                continue
            for v in ob.bound_box:
                w = ob.matrix_world @ Vector(v)
                xs.append(w.x)
                ys.append(w.y)
                zs.append(w.z)
    if not xs:
        return (0, 0, 10, 10, 0, 10)
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def line_mode(sc, white_override=True):
    """Black line work on transparent/white: override all materials, EEVEE, freestyle."""
    sc.render.engine = 'BLENDER_EEVEE'
    if white_override:
        wm = bpy.data.materials.get('linewhite')
        if wm is None:
            wm = bpy.data.materials.new('linewhite')
            wm.use_nodes = True
            b = wm.node_tree.nodes['Principled BSDF']
            b.inputs['Base Color'].default_value = (1, 1, 1, 1)
            b.inputs['Roughness'].default_value = 1.0
        sc.view_layers[0].material_override = wm
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = 0.0
    sc.render.use_freestyle = True
    freestyle(sc, thickness=1.5, crease=1.30)


def shot_plan(sc, outdir, name, names, pad=1.4, px=1700, bg='white'):
    show_only(names)
    x0, y0, z0, x1, y1, z1 = bbox(names)
    w, d = (x1 - x0) + pad, (y1 - y0) + pad
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if w >= d:
        rx, ry = px, max(200, int(px * d / w))
        oscale = w
    else:
        ry, rx = px, max(200, int(px * w / d))
        oscale = d
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    cam(sc, (cx, cy, 300), (cx, cy, 0), ortho=oscale)
    sc.render.filepath = os.path.join(outdir, name + '.png')
    bpy.ops.render.render(write_still=True)
    return (x0, y0, x1, y1, oscale)





def _lights(sc, S):
    for o in [o for o in bpy.data.objects if o.type == 'LIGHT']:
        bpy.data.objects.remove(o, do_unlink=True)
    add_sun(sc, elev=S.get('sun_elev', 46.0), rot=S.get('sun_rot', 128.0),
            energy=S.get('sun_energy', 3.2), angle=1.2)
    add_sun(sc, elev=22.0, rot=S.get('sun_rot', 128.0) + 168.0,
            energy=S.get('fill_energy', 0.55), angle=30.0)
    add_sun(sc, elev=66.0, rot=S.get('sun_rot', 128.0) + 55.0,
            energy=S.get('fill_energy', 0.55) * 0.7, angle=45.0)


def _cycles(sc, S, fast):
    sc.render.use_freestyle = False
    sc.view_layers[0].material_override = None
    set_cycles(sc, samples=24 if fast else S.get('samples', 110))
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = S.get('exposure', 0.0)



def _frame_pts(names, step=1.2, zmax=None):
    pts = []
    for cn in names:
        c = COLL.get(cn)
        if not c:
            continue
        for ob in c.objects:
            if ob.type != 'MESH' or ob.name in NOFRAME:
                continue
            for v in ob.bound_box:
                w = ob.matrix_world @ Vector(v)
                if zmax is not None and w.z > zmax:
                    continue
                pts.append(w)
    return pts


def fit_camera(sc, names, az, el, lens, res, tgt=None, margin=1.10,
               step=2.0, zmax=None, dist0=20.0):
    """Place a camera on the given bearing that frames `names` with margin."""
    import numpy as _np
    pts = _frame_pts(names, zmax=zmax)
    if not pts:
        pts = [Vector((0, 0, 0)), Vector((10, 10, 5))]
    P = _np.array([[p.x, p.y, p.z] for p in pts], dtype=float)
    ctr = P.mean(0)
    if tgt is None:
        tgt = Vector((float(ctr[0]), float(ctr[1]), float(ctr[2]) + 1.0))
    tgt = Vector((float(tgt[0]), float(tgt[1]), float(tgt[2])))
    P -= _np.array([tgt.x, tgt.y, tgt.z])
    e, a = math.radians(el), math.radians(az)
    d = _np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a),
                   math.sin(e)])
    fwd = -d
    up0 = _np.array([0.0, 0.0, 1.0])
    if abs(float(fwd @ up0)) > 0.999:
        up0 = _np.array([0.0, 1.0, 0.0])
    right = _np.cross(fwd, up0)
    right /= _np.linalg.norm(right)
    up = _np.cross(right, fwd)
    ar = res[0] / res[1]
    tanx = (36.0 / 2.0) / lens
    tany = tanx / ar
    dist = dist0
    for _ in range(60):
        loc = _np.array([tgt.x, tgt.y, tgt.z]) + d * dist
        rel = P - loc
        x = rel @ right
        y = rel @ up
        z = rel @ fwd                      # positive in front of camera
        need = max(
            float(_np.max(_np.abs(x) / (tanx * _np.maximum(z, 1e-6)))),
            float(_np.max(_np.abs(y) / (tany * _np.maximum(z, 1e-6)))),
        )
        if abs(need - margin) < 0.006:
            break
        dist *= (need / margin) ** 0.85 if need > 0 else 1.06
        dist = min(max(dist, 3.0), 600.0)
        if abs(need - margin) < 0.02:
            break
    loc = Vector((tgt.x + d[0] * dist, tgt.y + d[1] * dist, tgt.z + d[2] * dist))
    return cam(sc, loc, tgt, lens=lens), dist


def _massing_plinth(S, M):
    """Model base so the clay massing reads as an object, not a floating box."""
    fx0, fy0, fx1, fy1 = S['footprint']
    return box(fx0 - 2.6, fy0 - 2.6, -0.40, fx1 + 2.6, fy1 + 2.6, 0.02,
               M['white2'], 'L0')


def render_all(S, outdir, key, fast=False):
    cams = S['cameras']
    house = [f'L{i}' for i in range(len(S['levels']))] + ['ROOF']

    # ---------- pass 1: massing / clay study model ----------
    sc = reset()
    COLL.clear()
    NOFRAME.clear()
    M = build_materials(massing=True)
    build_scheme(S, M)
    _massing_plinth(S, M)
    # A white model on a white ground with a bright uniform world has no
    # tonal separation at all.  Cycles gives real contact shadow and corner
    # darkening, which is what makes a clay study model legible.
    studio_world(sc, 0.34, (0.63, 0.66, 0.72))
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 24 if fast else 64
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 6
    sc.render.use_freestyle = False
    sc.view_layers[0].material_override = None
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Filmic' if 'Filmic' in [
        v.name for v in sc.view_settings.bl_rna.properties['view_transform'].enum_items
    ] else 'Standard'
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = 0.12
    # stronger key light than the material pass: a clay study model needs a
    # readable shadow, not a flat white box
    _lights(sc, dict(S, sun_energy=S.get('sun_energy', 3.2) * 1.35,
                     fill_energy=S.get('fill_energy', 0.55) * 0.55))
    for nm, c in cams.items():
        if not nm.startswith('massing'):
            continue
        show_only(house)
        res = c.get('res', (1800, 1200))
        sc.render.resolution_x, sc.render.resolution_y = res
        fit_camera(sc, c.get('fit', house), c.get('az', -50.0),
                   c.get('el', 28.0), c.get('lens', 40), res,
                   tgt=c.get('target'), margin=c.get('margin', 1.04))
        sc.render.filepath = os.path.join(outdir, nm + '.png')
        bpy.ops.render.render(write_still=True)

    # ---------- pass 2: material render ----------
    sc = reset()
    COLL.clear()
    NOFRAME.clear()
    M = build_materials(massing=False)
    build_scheme(S, M)
    setup_world(sc, sun_elev=S.get('sun_elev', 46.0),
                sun_rot=S.get('sun_rot', 128.0), strength=S.get('sky', 0.30))
    _cycles(sc, S, fast)
    _lights(sc, S)
    interior_lights(S, energy=S.get('interior_energy', 46.0))
    reveal_fill(S, energy=S.get('reveal_energy', 18.0))
    # Alpha-blended glazing plus sealed interiors need headroom: the default
    # 6 bounces starves anything seen only through a window.
    sc.cycles.max_bounces = max(sc.cycles.max_bounces, 12)
    sc.cycles.diffuse_bounces = max(sc.cycles.diffuse_bounces, 8)
    sc.cycles.transparent_max_bounces = max(sc.cycles.transparent_max_bounces, 24)
    for nm, c in cams.items():
        if nm.startswith('massing'):
            continue
        show_only(house + ['SITE'])
        res = c.get('res', (1800, 1200))
        sc.render.resolution_x, sc.render.resolution_y = res
        fit_camera(sc, c.get('fit', house), c.get('az', -50.0),
                   c.get('el', 28.0), c.get('lens', 40), res,
                   tgt=c.get('target'), margin=c.get('margin', 1.04))
        sc.render.filepath = os.path.join(outdir, nm + '.png')
        bpy.ops.render.render(write_still=True)
    return True
