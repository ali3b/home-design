"""Rooftop solar for one concept: panel layout on the roof, hour-by-hour shading, and energy per month/season.

    python3 pipeline/solar.py concepts/c1_courtyard_house.json out/c1

Writes out/<key>/solar.json (panel geometry for Blender/Unity plus the results) and docs/solar_<key>.json
(results only, for the Pages calculator).

Method
- Weather: PVGIS-ERA5 typical meteorological year (hourly GHI, DNI, DHI, air temperature), fetched once for the
  site rounded to whole degrees and cached in out/_cache (gitignored). Nothing location-specific is written to
  the outputs: they carry only the rounded latitude, as the timelapse does.
- Roof surfaces come from the concept's `roofs`, using the same geometry rules as the Blender model
  (pipeline/lib/bbuild.hip, build_flat_roof, build_skylight, build_lean).
- Panels: 1.722 x 1.134 m, 440 Wp modules. Flush on pitched roofs (0.12 m stand-off); on flat roofs in
  10 deg south-facing rows spaced for no row-to-row shading at winter-solstice noon.
- Shading: rays from 6 points on every panel to the sun every hour of the year, against the two assumed 3-storey
  neighbours, the house's own roofs, parapets and lanterns, and the other panels. Diffuse light uses each point's
  sky-view factor from the same obstacles (isotropic sky). Ground reflection with albedo 0.2.
- Output: incidence-angle loss (ASHRAE, b0 0.05), cell temperature (NOCT 45 C rack / 48 C flush,
  -0.34 %/K) and 14 % system losses (inverter, wiring, soiling, mismatch), the same default as PVGIS. Partial
  shading is averaged over each panel, which assumes module-level electronics (micro-inverters or optimisers).
- The run is repeated without the neighbours, to show what the assumed neighbours cost.
- Recommended array: panels whose own yield is at least KEEP x that of an unshaded panel at the best orientation.
"""
import json
import math
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PANEL_L, PANEL_W, PANEL_WP = 1.722, 1.134, 440.0
GAP = 0.02
EDGE = 0.30            # clearance from eaves, ridges, hips and verges on pitched roofs
PARAPET_CLEAR = 0.45   # clearance from the inner face of a parapet (access, drainage)
FLAT_TILT = 10.0
STANDOFF = 0.12
LOSS = 0.14
KEEP = 0.70
ALBEDO = 0.2
CAL = 0.966            # brings unshaded results onto PVGIS PVcalc (10 S, 35 E, 35 W all within 1 %)
SEASONS = [("Winter", "Dec–Feb", (12, 1, 2)), ("Spring", "Mar–May", (3, 4, 5)),
           ("Summer", "Jun–Aug", (6, 7, 8)), ("Autumn", "Sep–Nov", (9, 10, 11))]
MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


# ------------------------------------------------------------------ weather --
def tmy():
    cache = os.path.join(ROOT, 'out', '_cache', 'tmy.json')
    if os.path.exists(cache):
        return json.load(open(cache))
    priv = json.load(open(os.path.join(ROOT, 'concepts', 'site.private.json')))
    lat, lon = round(priv['lat']), round(priv['lon'])          # whole degrees only
    url = f"https://re.jrc.ec.europa.eu/api/v5_3/tmy?lat={lat}&lon={lon}&outputformat=json"
    d = json.load(urllib.request.urlopen(url, timeout=60))
    rows = [{k: r[k] for k in ('time(UTC)', 'T2m', 'G(h)', 'Gb(n)', 'Gd(h)')} for r in d['outputs']['tmy_hourly']]
    out = {'lat': lat, 'lon': lon, 'source': 'PVGIS 5.3 TMY (ERA5)', 'hourly': rows}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(out, open(cache, 'w'))
    return out


def sun_vectors(times, lat, lon):
    """Unit vectors to the sun (x east, y north, z up) at the middle of each UTC hour."""
    out = []
    for t in times:
        mo, dd, hh = int(t[4:6]), int(t[6:8]), int(t[9:11])
        doy = sum(MDAYS[:mo - 1]) + dd
        g = 2 * math.pi / 365 * (doy - 1 + (hh + 0.5 - 12) / 24)
        eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                        - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
        decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
                + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
        tst = (hh + 0.5) * 60 + eot + 4 * lon
        H = math.radians(tst / 4 - 180)
        p = math.radians(lat)
        sel = math.sin(p) * math.sin(decl) + math.cos(p) * math.cos(decl) * math.cos(H)
        el = math.asin(max(-1, min(1, sel)))
        az = math.atan2(math.sin(H), math.cos(H) * math.sin(p) - math.tan(decl) * math.cos(p)) + math.pi
        out.append((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    return np.array(out)


def beam_normal(ghi, dhi, sun):
    """Direct-normal from the hourly horizontal beam (GHI - DHI) and the sun at mid-hour. The TMY's own DNI
    column does not close with GHI at low sun, which skews east- against west-facing roofs."""
    s = sun[:, 2]
    return np.minimum(np.where(s > 0.03, (ghi - dhi) / np.maximum(s, 0.03), 0.0), 1100.0)


# ------------------------------------------------------------------ geometry --
def quad(*p):
    return [tuple(map(float, q)) for q in p]


def box_tris(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (0, 3, 2, 1)]
    return [[v[i] for i in q] for q in f]


def hip_faces(r):
    """Same faces as pipeline/lib/bbuild.hip (eave slopes, flat top, vertical ends)."""
    o = r.get('overhang', 0.6)
    ox0, oy0, ox1, oy1 = r['x0'] - o, r['y0'] - o, r['x1'] + o, r['y1'] + o
    ze, zr = r['ze'], r['zr']
    dx, dy = ox1 - ox0, oy1 - oy0
    along_y = dy >= dx
    long_, short_ = (dy, dx) if along_y else (dx, dy)
    rf = max(0.0, min(0.95, (long_ - short_) / long_))
    rx0, ry0, rx1, ry1 = (oy0, ox0, oy1, ox1) if along_y else (ox0, oy0, ox1, oy1)
    h = ry1 - ry0
    a0, a1 = ry0 + h * (1 - rf) / 2, ry1 - h * (1 - rf) / 2
    faces = [[(rx0, ry0, ze), (rx1, ry0, ze), (rx1, a0, zr), (rx0, a0, zr)],
             [(rx0, a0, zr), (rx1, a0, zr), (rx1, a1, zr), (rx0, a1, zr)],
             [(rx0, a1, zr), (rx1, a1, zr), (rx1, ry1, ze), (rx0, ry1, ze)],
             [(rx0, ry0, ze), (rx0, a0, zr), (rx0, a1, zr), (rx0, ry1, ze)],
             [(rx1, ry0, ze), (rx1, a0, zr), (rx1, a1, zr), (rx1, ry1, ze)]]
    if along_y:
        faces = [[(y, x, z) for x, y, z in f] for f in faces]
    return faces


def up_normal(poly):
    p = np.array(poly)
    n = np.cross(p[1] - p[0], p[2] - p[0])
    if np.linalg.norm(n) < 1e-9:
        n = np.cross(p[2] - p[0], p[3] - p[0])
    n = n / np.linalg.norm(n)
    return -n if n[2] < 0 else n


def surfaces_and_obstacles(C, S):
    """Mountable roof surfaces and the house's own shading geometry."""
    surf, obst = [], []
    for i, r in enumerate(C['roofs']):
        kind = r.get('kind', 'hip')
        name = r.get('name') or roof_label(r, C['roofs'])
        obst += box_tris(r['x0'] + 0.05, r['y0'] + 0.05, 0.0, r['x1'] - 0.05, r['y1'] - 0.05,
                         r.get('ze', r.get('zlow', 3.0)) - 0.05)                   # the storey under the roof
        if kind in ('hip', 'gable'):
            for f in hip_faces(r):
                obst.append(f)
                n = up_normal(f)
                if n[2] > 0.99:
                    surf.append({'name': f"{name} flat top", 'kind': 'flat', 'z': f[0][2],
                                 'rect': rect_of(f), 'clear': EDGE})
                elif n[2] > 0.2:
                    surf.append({'name': f"{name} {facing(n)} slope", 'kind': 'pitched', 'poly': f})
        elif kind == 'flat':
            o = r.get('overhang', 0.0)
            x0, y0, x1, y1 = r['x0'] - o, r['y0'] - o, r['x1'] + o, r['y1'] + o
            pt = 0.2
            obst.append(quad((x0, y0, r['ze']), (x1, y0, r['ze']), (x1, y1, r['ze']), (x0, y1, r['ze'])))
            for a in ((x0, y0, x1, y0 + pt), (x0, y1 - pt, x1, y1), (x0, y0, x0 + pt, y1), (x1 - pt, y0, x1, y1)):
                obst += box_tris(a[0], a[1], r['ze'] - 0.3, a[2], a[3], r['zr'])
            surf.append({'name': f"{name} flat roof", 'kind': 'flat', 'z': r['ze'],
                         'rect': (x0 + pt, y0 + pt, x1 - pt, y1 - pt), 'clear': PARAPET_CLEAR,
                         'parapet': r['zr'] - r['ze']})
        elif kind == 'skylight':
            x0, y0, x1, y1, ze = r['x0'], r['y0'], r['x1'], r['y1'], r['ze']
            gx0, gy0, gx1, gy1 = r['glass']
            zd = ze + 0.25
            obst.append(quad((x0, y0, zd), (x1, y0, zd), (x1, y1, zd), (x0, y1, zd)))
            obst += box_tris(gx0, gy0, zd, gx1, gy1, r['zr'])                      # glazed lantern
            for (a0, b0, a1, b1) in ((x0, y0, gx0, y1), (gx1, y0, x1, y1)):
                if a1 - a0 > 1.2:
                    surf.append({'name': f"{name} flat deck", 'kind': 'flat', 'z': zd, 'rect': (a0, b0, a1, b1),
                                 'clear': EDGE})
        elif kind == 'lean':
            x0, y0, x1, y1, zl, zh = r['x0'], r['y0'], r['x1'], r['y1'], r['zlow'], r['zhigh']
            f = quad((x0, y0, zl), (x1, y0, zh), (x1, y1, zh), (x0, y1, zl))
            obst.append(f)
            surf.append({'name': name, 'kind': 'pitched', 'poly': f})
    for f in C.get('features', []):
        x0, y0, x1, y1 = f['rect']
        obst += box_tris(x0, y0, f['z'][0], x1, y1, f['z'][1])
    return surf, obst


def roof_label(r, roofs):
    area = lambda q: (q['x1'] - q['x0']) * (q['y1'] - q['y0'])
    if r.get('kind') == 'lean':
        return 'Side lean-to roof'
    if area(r) < 15:
        return 'Porch roof' if r['y1'] < 4 else 'Alfresco roof' if r['y0'] > 15 else 'Small roof'
    big = [q for q in roofs if area(q) >= 15 and q.get('kind') != 'lean']
    if len(big) == 1:
        return 'Main roof'
    cy = (r['y0'] + r['y1']) / 2
    return 'Front roof' if cy < 8 else 'Rear roof' if cy > 12 else 'Middle roof'


def neighbour_obstacles(site):
    out = []
    for n in site.get('neighbours', []):
        out += box_tris(n['x0'], n['y0'], 0.0, n['x1'], n['y1'], n['height'])
    return out


def rect_of(f):
    xs, ys = [p[0] for p in f], [p[1] for p in f]
    return (min(xs), min(ys), max(xs), max(ys))


def facing(n):
    az = math.degrees(math.atan2(n[0], n[1])) % 360
    return ['north', 'east', 'south', 'west'][int(((az + 45) % 360) // 90)]


# ------------------------------------------------------------------- layout --
def panel(c, u, v, n, w, l, tilt, az, surf):
    c, u, v, n = map(np.asarray, (c, u, v, n))
    corners = [c - u * w / 2 - v * l / 2, c + u * w / 2 - v * l / 2, c + u * w / 2 + v * l / 2, c - u * w / 2 + v * l / 2]
    return {'c': c, 'u': u, 'v': v, 'n': n, 'w': w, 'l': l, 'tilt': tilt, 'az': az, 'surface': surf,
            'corners': [list(map(lambda q: round(float(q), 3), k)) for k in corners]}


def layout_pitched(s):
    """Grid of flush panels inside the (convex) roof plane, kept EDGE clear of every edge."""
    P = np.array(s['poly'])
    n = up_normal(s['poly'])
    v = np.array([0.0, 0.0, 1.0]) - n * n[2]                 # up-slope in the plane
    v /= np.linalg.norm(v)
    u = np.cross(v, n)
    o = P[0]
    q = np.array([[(p - o) @ u, (p - o) @ v] for p in P])
    # convex polygon as inward half-planes, shifted inwards by EDGE
    cen = q.mean(axis=0)
    hp = []
    for i in range(len(q)):
        a, b = q[i], q[(i + 1) % len(q)]
        e = b - a
        if np.linalg.norm(e) < 1e-6:
            continue
        nn = np.array([-e[1], e[0]]) / np.linalg.norm(e)
        if (cen - a) @ nn < 0:
            nn = -nn
        hp.append((nn, a @ nn + EDGE))

    def inside(pt):
        return all(pt @ nn >= d - 1e-6 for nn, d in hp)

    tilt = math.degrees(math.acos(n[2]))
    az = math.degrees(math.atan2(n[0], n[1])) % 360
    best = []
    for (w, l) in ((PANEL_W, PANEL_L), (PANEL_L, PANEL_W)):          # portrait, landscape
        for su in np.linspace(0, w, 6, endpoint=False):
            for sv in np.linspace(0, l, 4, endpoint=False):
                got = []
                umin, vmin = q[:, 0].min() + su, q[:, 1].min() + sv
                nu = int((q[:, 0].max() - umin) / (w + GAP)) + 1
                nv = int((q[:, 1].max() - vmin) / (l + GAP)) + 1
                for i in range(nu):
                    for j in range(nv):
                        a = np.array([umin + i * (w + GAP), vmin + j * (l + GAP)])
                        cs = [a, a + [w, 0], a + [w, l], a + [0, l]]
                        if all(inside(cc) for cc in cs):
                            cc = a + [w / 2, l / 2]
                            got.append(o + u * cc[0] + v * cc[1] + n * STANDOFF)
                if len(got) > len(best):
                    best = [(g, w, l) for g in got]
    return [panel(c, u, v, n, w, l, tilt, az, s['name']) for c, w, l in best]


def layout_flat(s):
    """South-facing rows at FLAT_TILT, portrait, spaced for no shading at winter-solstice noon (lat 21)."""
    x0, y0, x1, y1 = s['rect']
    cl = s['clear']
    x0, y0, x1, y1 = x0 + cl, y0 + cl, x1 - cl, y1 - cl
    t = math.radians(FLAT_TILT)
    depth, rise = PANEL_L * math.cos(t), PANEL_L * math.sin(t)
    noon_el = math.radians(90 - 21 - 23.44)
    pitch = depth + rise / math.tan(noon_el) + 0.15
    if x1 - x0 < PANEL_W or y1 - y0 < depth:
        return []
    nx = int((x1 - x0 + GAP) / (PANEL_W + GAP))
    ny = int((y1 - y0 - depth) / pitch) + 1
    sx = x0 + (x1 - x0 - (nx * PANEL_W + (nx - 1) * GAP)) / 2
    n = np.array([0.0, -math.sin(t), math.cos(t)])          # faces south (-y)
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.0, math.cos(t), math.sin(t)])           # up-slope towards north
    out = []
    for j in range(ny):
        yc = y0 + j * pitch + depth / 2
        for i in range(nx):
            xc = sx + i * (PANEL_W + GAP) + PANEL_W / 2
            c = np.array([xc, yc, s['z'] + 0.25 + rise / 2])
            out.append(panel(c, u, v, n, PANEL_W, PANEL_L, FLAT_TILT, 180.0, s['name']))
    return out


# ----------------------------------------------------------------- shading --
def tris_of(polys):
    T = []
    for p in polys:
        for k in range(1, len(p) - 1):
            T.append((p[0], p[k], p[k + 1]))
    return np.array(T, dtype=float)


def visible(P, D, T, chunk=60):
    """bool [len(P), len(D)]: ray from each point along each direction misses every triangle."""
    vis = np.ones((len(P), len(D)), bool)
    for tri in T:
        v0, e1, e2 = tri[0], tri[1] - tri[0], tri[2] - tri[0]
        pvec = np.cross(D, e2)
        det = pvec @ e1
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        tvec = P - v0
        u = (tvec @ pvec.T) * inv
        m = (u >= 0) & (u <= 1)
        if not m.any():
            continue
        qvec = np.cross(tvec, e1)
        v = (qvec @ D.T) * inv
        m &= (v >= 0) & (u + v <= 1)
        if not m.any():
            continue
        t = (qvec @ e2)[:, None] * inv
        m &= (t > 1e-3) & ok
        vis &= ~m
    return vis


def sample_points(p):
    pts = []
    for a in (-0.25, 0.25):
        for b in (-1 / 3, 0.0, 1 / 3):
            pts.append(p['c'] + p['u'] * a * p['w'] + p['v'] * b * p['l'] + p['n'] * 0.03)
    return pts


def sky_dirs(n=1200):
    i = np.arange(n) + 0.5
    z = 1 - i / n                                  # upper hemisphere, uniform in solid angle
    r = np.sqrt(1 - z * z)
    ph = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([r * np.cos(ph), r * np.sin(ph), z], axis=1)


def simulate(panels, obst_polys, W, sun, lat):
    T = tris_of(obst_polys + [[tuple(c) for c in p['corners']] for p in panels])
    P = np.array([pt for p in panels for pt in sample_points(p)])
    npp = 6
    up = sun[:, 2] > 0.01
    D = sun[up]
    vis_sun = visible(P, D, T).reshape(len(panels), npp, -1).mean(axis=1)            # [panel, up-hours]
    SD = sky_dirs()
    vis_sky = visible(P, SD, T).reshape(len(panels), npp, -1)
    ghi = np.array([r['G(h)'] for r in W])
    dhi = np.array([r['Gd(h)'] for r in W])
    dni = beam_normal(ghi, dhi, sun)
    ta = np.array([r['T2m'] for r in W])
    hours = len(W)
    out = np.zeros((len(panels), hours))
    for k, p in enumerate(panels):
        n = p['n']
        cosd = np.clip(SD @ n, 0, None)
        svf = (vis_sky[k] * cosd[None, :]).sum(axis=1).mean() * 2 / len(SD)          # isotropic sky view
        cosi = np.clip(sun @ n, 0, None)
        beam = np.zeros(hours)
        beam[up] = dni[up] * cosi[up] * vis_sun[k]
        iam = np.clip(1 - 0.05 * (1 / np.maximum(cosi, 1e-3) - 1), 0, 1)
        poa = beam * iam + dhi * svf * 0.95 + ghi * ALBEDO * (1 - n[2]) / 2
        noct = 45.0 if p['surface'].endswith(('flat roof', 'flat top', 'flat deck')) else 48.0
        tc = ta + poa * (noct - 20) / 800
        out[k] = PANEL_WP / 1000 * poa / 1000 * (1 + -0.0034 * (tc - 25)) * (1 - LOSS) * CAL   # kWh per hour
        p['svf'] = round(float(svf), 3)
    return out


def reference_kwh_per_kwp(W, sun):
    """Unshaded 1 kWp at the best fixed orientation (tilt 10-25, south) - the yardstick for KEEP."""
    best = 0
    for tilt in (5, 10, 15, 20, 25):
        t = math.radians(tilt)
        n = np.array([0, -math.sin(t), math.cos(t)])
        ghi = np.array([r['G(h)'] for r in W]); dhi = np.array([r['Gd(h)'] for r in W])
        dni = beam_normal(ghi, dhi, sun); ta = np.array([r['T2m'] for r in W])
        cosi = np.clip(sun @ n, 0, None) * (sun[:, 2] > 0.01)
        iam = np.clip(1 - 0.05 * (1 / np.maximum(cosi, 1e-3) - 1), 0, 1)
        poa = dni * cosi * iam + dhi * (1 + n[2]) / 2 * 0.95 + ghi * ALBEDO * (1 - n[2]) / 2
        tc = ta + poa * 25 / 800
        e = (poa / 1000 * (1 - 0.0034 * (tc - 25)) * (1 - LOSS) * CAL).sum()
        best = max(best, e)
    return best


# ---------------------------------------------------------------- economics --
# Defaults are editable on the Pages calculator (docs/solar.html), which repeats this model in JavaScript.
ECON = {
    'tiers': [[100, 1901], [100, 2289], [200, 2894], [300, 3456], [None, 3844]],   # VND/kWh ex VAT, from 1 Nov 2026
    'vat': 0.08,
    'cost_per_kwp': 14_000_000,        # VND installed, incl. module-level electronics (shaded roofs)
    'export_price': 0,                 # VND/kWh paid for surplus: conservative (rate not yet published)
    'export_cap': 0.20,                # share of output that may be sold (Decree 58/2025)
    'om_pct': 0.01,                    # cleaning, checks, inverter fund: share of cost per year
    'degradation': 0.005,
    'years': 25,
    # example 4-bedroom household with air-conditioning, kWh per month Jan..Dec (about 7,000 kWh a year)
    'load_monthly': [350, 330, 380, 500, 750, 850, 900, 850, 700, 500, 400, 380],
}
BASE_SHAPE = [2, 2, 2, 2, 2, 3, 6, 6, 4, 3, 3, 3, 4, 3, 3, 3, 4, 6, 9, 9, 8, 7, 5, 3]     # lights, cooking, fridge
COOL_SHAPE = [6, 6, 6, 6, 5, 4, 2, 1, 1, 2, 3, 4, 5, 6, 6, 6, 5, 4, 5, 6, 7, 7, 7, 7]     # air-con: afternoons, nights


def load_profile(monthly):
    """Hourly household demand for one mean day of each month (kWh), from the monthly total."""
    base_m = min(monthly)
    out = []
    for m, tot in enumerate(monthly):
        b = [v / sum(BASE_SHAPE) * base_m / MDAYS[m] for v in BASE_SHAPE]
        extra = max(0, tot - base_m) / MDAYS[m]
        c = [v / sum(COOL_SHAPE) * extra for v in COOL_SHAPE]
        out.append([b[h] + c[h] for h in range(24)])
    return out


def bill(kwh, e=ECON):
    left, cost = kwh, 0.0
    for size, price in e['tiers']:
        take = left if size is None else min(left, size)
        cost += take * price
        left -= take
        if left <= 0:
            break
    return cost * (1 + e['vat'])


def economics(gen_hourly, W, kwp, e=ECON):
    """Year-one bill with and without the array, then simple payback and 25-year net saving."""
    mon = months_of(W)
    hr = np.array([(int(r['time(UTC)'][9:11]) + 7) % 24 for r in W])
    lp = np.array(load_profile(e['load_monthly']))
    load = lp[mon - 1, hr]
    self_use = np.minimum(gen_hourly, load)
    export = gen_hourly - self_use
    before = after = 0.0
    for m in range(1, 13):
        k = mon == m
        before += bill(e['load_monthly'][m - 1])
        after += bill(max(0.0, e['load_monthly'][m - 1] - self_use[k].sum()))
    sold = min(export.sum(), e['export_cap'] * gen_hourly.sum())
    cost = kwp * e['cost_per_kwp']
    save1 = before - after + sold * e['export_price']
    total, payback, cum = 0.0, None, -cost
    for y in range(e['years']):
        s_y = save1 * (1 - e['degradation']) ** y - cost * e['om_pct']
        cum += s_y
        total += s_y
        if payback is None and cum >= 0:
            payback = y + 1 - cum / s_y if s_y > 0 else None
    return {'cost': round(cost), 'bill_before': round(before), 'bill_after': round(after),
            'saving_year1': round(save1), 'self_used_kwh': round(float(self_use.sum())),
            'exported_kwh': round(float(export.sum())), 'self_use_pct': round(100 * float(self_use.sum() / max(gen_hourly.sum(), 1))),
            'covers_pct': round(100 * float(self_use.sum()) / sum(e['load_monthly'])),
            'payback_years': round(payback, 1) if payback else None, 'net_25y': round(total - cost)}


BATT_COST = 5_000_000          # VND per usable kWh, lithium iron phosphate incl. hybrid-inverter share
BATT_REPLACE = (12, 0.6)       # replaced in year 13 at 60 % of today's price
HOUSEHOLDS = {'no_ac': ('Without air-con', [300] * 12),
              'ac': ('With air-con', ECON['load_monthly'])}


def battery_run(gen, load, B, eff=0.95, reserve=0.1, years=2):
    """Hourly dispatch: surplus charges the battery, shortfall draws from it, the rest comes from the grid
    (or a generator, off-grid). Runs the year twice so the start state does not matter. Returns grid kWh per hour."""
    lo, soc = reserve * B, 0.5 * B
    g, l = gen.tolist(), load.tolist()
    imp = [0.0] * len(g)
    for _ in range(years):
        for i in range(len(g)):
            d = g[i] - l[i]
            if d >= 0:
                soc = min(B, soc + d * eff)
                imp[i] = 0.0
            else:
                out = min(-d, max(0.0, (soc - lo) * eff))
                soc -= out / eff
                imp[i] = -d - out
    return np.array(imp)


def battery_case(gen, W, n_panels, B, loadm, e=ECON):
    mon = months_of(W)
    hr = np.array([(int(r['time(UTC)'][9:11]) + 7) % 24 for r in W])
    load = np.array(load_profile(loadm))[mon - 1, hr]
    imp = battery_run(gen, load, B)
    before = sum(bill(x, e) for x in loadm)
    after = sum(bill(imp[mon == m].sum(), e) for m in range(1, 13))
    pv, bc = n_panels * PANEL_WP / 1000 * e['cost_per_kwp'], B * BATT_COST
    save = before - after
    cum, pay, tot = -(pv + bc), None, 0.0
    for y in range(e['years']):
        s_y = save * (1 - e['degradation']) ** y - pv * e['om_pct'] - (bc * BATT_REPLACE[1] if y == BATT_REPLACE[0] else 0)
        cum += s_y; tot += s_y
        if pay is None and cum >= 0 and s_y > 0:
            pay = y + 1 - cum / s_y
    seas = {}
    for nm, _, ms in SEASONS:
        k = np.isin(mon, ms)
        seas[nm] = round(100 * (1 - imp[k].sum() / load[k].sum()))
    daily = imp.reshape(-1, 24).sum(axis=1)
    short = daily > 0.3
    run = best = 0
    for v in short:
        run = run + 1 if v else 0
        best = max(best, run)
    return {'panels': n_panels, 'kwp': round(n_panels * PANEL_WP / 1000, 1), 'battery_kwh': B,
            'cost': round(pv + bc), 'sun_share_pct': round(100 * (1 - imp.sum() / load.sum())), 'seasons_pct': seas,
            'grid_free_days': int((~short).sum()), 'grid_kwh': round(float(imp.sum())),
            'longest_short_run_days': best, 'worst_day_grid_kwh': round(float(daily.max()), 1),
            'saving_year1': round(save), 'payback_years': round(pay, 1) if pay else None, 'net_25y': round(tot - pv - bc),
            'bill_before': round(before)}


def battery_study(hourly, keep, spec, W, n_best):
    """Grid-connected battery comparison, and an off-grid test using every panel that fits."""
    order = sorted(keep, key=lambda i: -spec[i])
    gen = lambda idx: hourly[idx].sum(axis=0)
    out = {'battery_cost_per_kwh': BATT_COST, 'households': {}}
    for hk, (label, loadm) in HOUSEHOLDS.items():
        rows = []
        for n in sorted({n_best, len(order)}):
            for B in (0, 5, 10, 15):
                rows.append(battery_case(gen(order[:n]), W, n, B, loadm))
        allp = list(range(len(hourly)))
        off = []
        for nm, idx in (('recommended', order), ('every panel that fits', allp)):
            for B in (10, 20, 40):
                c = battery_case(gen(idx), W, len(idx), B, loadm)
                c['array'] = nm
                off.append(c)
        out['households'][hk] = {'label': label, 'year_kwh': sum(loadm), 'grid_tied': rows, 'off_grid': off}
    return out


def best_size(hourly, keep, spec, W):
    """Number of panels (best first) with the largest 25-year net saving under the default assumptions."""
    order = sorted(keep, key=lambda i: -spec[i])
    best = None
    for n in range(2, len(order) + 1):
        ec = economics(hourly[order[:n]].sum(axis=0), W, n * PANEL_WP / 1000)
        if best is None or ec['net_25y'] > best[1]['net_25y']:
            best = (n, ec)
    return best


# --------------------------------------------------------------------- main --
def months_of(W):
    return np.array([int(r['time(UTC)'][4:6]) for r in W])


def summarise(hourly, W, idx):
    """kWh by month and season, and a 12x24 mean-day profile (local solar-ish time, UTC+7) for the calculator."""
    mon = months_of(W)
    hr = np.array([(int(r['time(UTC)'][9:11]) + 7) % 24 for r in W])
    tot = hourly[idx].sum(axis=0) if len(idx) else np.zeros(len(W))
    monthly = [float(tot[mon == m].sum()) for m in range(1, 13)]
    seasons = []
    for nm, lab, ms in SEASONS:
        e = sum(monthly[m - 1] for m in ms)
        days = sum(MDAYS[m - 1] for m in ms)
        seasons.append({'season': nm, 'months': lab, 'kwh': round(e), 'kwh_per_day': round(e / days, 1)})
    prof = [[round(float(tot[(mon == m) & (hr == h)].sum() / MDAYS[m - 1]), 3) for h in range(24)] for m in range(1, 13)]
    return {'monthly_kwh': [round(x) for x in monthly], 'seasons': seasons, 'year_kwh': round(sum(monthly)),
            'profile_kwh': prof}


def main():
    cpath, outdir = sys.argv[1], sys.argv[2]
    C = json.load(open(cpath))
    site = json.load(open(os.path.join(ROOT, 'concepts', 'site.json')))
    key = C.get('key', os.path.basename(outdir)).lower()
    W_ = tmy()
    W = W_['hourly']
    sun = sun_vectors([r['time(UTC)'] for r in W], W_['lat'], W_['lon'])
    surf, own = surfaces_and_obstacles(C, site)
    neigh = neighbour_obstacles(site)
    panels = []
    for s in surf:
        got = layout_pitched(s) if s['kind'] == 'pitched' else layout_flat(s)
        panels += got
    ref = reference_kwh_per_kwp(W, sun)
    hourly = simulate(panels, own + neigh, W, sun, W_['lat'])
    hourly_open = simulate(panels, own, W, sun, W_['lat'])
    spec = hourly.sum(axis=1) / (PANEL_WP / 1000)
    spec_open = hourly_open.sum(axis=1) / (PANEL_WP / 1000)
    keep = [i for i in range(len(panels)) if spec[i] >= KEEP * ref]
    allp = list(range(len(panels)))
    # per-surface table
    by = {}
    for i, p in enumerate(panels):
        b = by.setdefault(p['surface'], {'surface': p['surface'], 'tilt': round(p['tilt']), 'azimuth': round(p['az']),
                                         'panels': 0, 'kept': 0, 'kwh': 0.0, 'kwh_open': 0.0})
        b['panels'] += 1
        b['kwh'] += float(hourly[i].sum()); b['kwh_open'] += float(hourly_open[i].sum())
        if i in keep:
            b['kept'] += 1
    for b in by.values():
        b['kwh_per_kwp'] = round(b['kwh'] / (b['panels'] * PANEL_WP / 1000))
        b['kwh_per_kwp_no_neighbours'] = round(b['kwh_open'] / (b['panels'] * PANEL_WP / 1000))
        b['kwh'] = round(b['kwh']); b['kwh_open'] = round(b['kwh_open'])
    res = {
        'key': key.upper(), 'title': C.get('title', key),
        'assumptions': {'latitude': f"{W_['lat']}°N (rounded)", 'weather': W_['source'] + ', typical year',
                        'module': f"{PANEL_WP:.0f} Wp, {PANEL_L} × {PANEL_W} m", 'system_losses': LOSS,
                        'flat_roof_tilt_deg': FLAT_TILT, 'keep_threshold': KEEP,
                        'reference_kwh_per_kwp': round(ref),
                        'neighbours': site.get('neighbours_note', '')},
        'recommended': {'panels': len(keep), 'kwp': round(len(keep) * PANEL_WP / 1000, 2),
                        **summarise(hourly, W, keep),
                        'year_kwh_no_neighbours': round(float(hourly_open[keep].sum())) if keep else 0},
        'all_that_fit': {'panels': len(panels), 'kwp': round(len(panels) * PANEL_WP / 1000, 2),
                         **{k: v for k, v in summarise(hourly, W, allp).items() if k != 'profile_kwh'}},
        'surfaces': list(by.values()),
        'economics': {'assumptions': {k: v for k, v in ECON.items()},
                      'recommended': economics(hourly[keep].sum(axis=0), W, len(keep) * PANEL_WP / 1000) if keep else None},
        'hourly_kwh': [round(float(x), 2) for x in (hourly[keep].sum(axis=0) if keep else np.zeros(len(W)))],
        'hourly_note': 'hourly_kwh[i]: hour i of a 365-day year from 1 Jan 00:00 UTC; local time is UTC+7',
        'panel_yields_kwh': sorted([round(float(hourly[i].sum()), 1) for i in keep], reverse=True),
        'panels': [{'corners': p['corners'], 'surface': p['surface'], 'tilt': round(p['tilt'], 1),
                    'kwh_per_kwp': round(float(spec[i])), 'kwh_per_kwp_no_neighbours': round(float(spec_open[i])),
                    'keep': i in keep} for i, p in enumerate(panels)],
    }
    if keep:
        n, ec = best_size(hourly, keep, spec, W)
        res['economics']['best_size'] = {'panels': n, 'kwp': round(n * PANEL_WP / 1000, 2), **ec}
        res['batteries'] = battery_study(hourly, keep, spec, W, n)
    os.makedirs(outdir, exist_ok=True)
    json.dump(res, open(os.path.join(outdir, 'solar.json'), 'w'), indent=1)
    pub = {k: v for k, v in res.items()}
    json.dump(pub, open(os.path.join(ROOT, 'docs', f'solar_{key}.json'), 'w'), separators=(',', ':'))
    r = res['recommended']
    print(f"SOLAR_OK {key}: {len(panels)} panels fit, {r['panels']} kept = {r['kwp']} kWp, "
          f"{r['year_kwh']} kWh/yr ({r['year_kwh_no_neighbours']} without neighbours), ref {ref:.0f} kWh/kWp")
    ec = res['economics']
    print(f"   econ: recommended {ec['recommended']}")
    print(f"   econ: best size {ec.get('best_size')}")
    for hk, h in res.get('batteries', {}).get('households', {}).items():
        for c in h['grid_tied'] + h['off_grid']:
            print(f"   {hk:5s} {c.get('array', 'grid'):22s} {c['panels']:2d}p B{c['battery_kwh']:2d} sun {c['sun_share_pct']:3d}% "
                  f"{c['seasons_pct']} free {c['grid_free_days']:3d} gridkWh {c['grid_kwh']:5d} run {c['longest_short_run_days']:3d} "
                  f"worst {c['worst_day_grid_kwh']} pay {c['payback_years']} net {c['net_25y']/1e6:.0f}M")
    for s in r['seasons']:
        print(f"   {s['season']:7s} {s['kwh']:6d} kWh  {s['kwh_per_day']:5.1f}/day")
    for b in by.values():
        print(f"   {b['surface']:28s} tilt {b['tilt']:3d} az {b['azimuth']:3d}  {b['panels']:3d} fit {b['kept']:3d} kept"
              f"  {b['kwh_per_kwp']:5d} kWh/kWp  (no neighbours {b['kwh_per_kwp_no_neighbours']})")


if __name__ == '__main__':
    main()
