"""Rectilinear wall derivation — pure Python, no Blender.

Single source of truth for both the 3D build (lib/bbuild.py) and the
drawing sheets (lib/sheetgen.py), so plans can never disagree with the model.

Convention: a wall's `axis` is the direction it RUNS.  `axis='x'` means the
wall runs along X at a constant Y (`coord`).  `axis='y'` runs along Y at a
constant X.
"""
EPS = 0.02


def derive(rooms, fp, doors=(), kind_of=None):
    """rooms: list of (name, x0, y0, x1, y1, kind).  Returns wall dicts."""
    fx0, fy0, fx1, fy1 = fp
    horiz = {}
    vert = {}
    for nm, x0, y0, x1, y1, kind in rooms:
        horiz.setdefault(round(y0, 3), []).append((x0, x1, nm))
        horiz.setdefault(round(y1, 3), []).append((x0, x1, nm))
        vert.setdefault(round(x0, 3), []).append((y0, y1, nm))
        vert.setdefault(round(x1, 3), []).append((y0, y1, nm))
    walls = []

    def merge(bucket, axis):
        out = []
        for coord, segs in bucket.items():
            segs = sorted(segs)
            cur = None
            for a, b, nm in segs:
                if cur and a <= cur[1] + EPS:
                    cur[1] = max(cur[1], b)
                    cur[2].append(nm)
                else:
                    if cur:
                        out.append(cur)
                    cur = [a, b, [nm]]
            if cur:
                out.append(cur)
            walls.extend([dict(axis=axis, coord=coord, t0=a, t1=b,
                               rooms=tuple(dict.fromkeys(nms))) for a, b, nms in out])

    merge(horiz, 'x')
    merge(vert, 'y')
    seen = {}
    keep = []
    for w in walls:
        k = (w['axis'], round(w['coord'], 3), round(w['t0'], 3), round(w['t1'], 3))
        if k in seen:
            seen[k]['rooms'] = tuple(dict.fromkeys(seen[k]['rooms'] + w['rooms']))
            continue
        seen[k] = w
        keep.append(w)
    walls = keep
    for w in walls:
        c, a, b = w['coord'], w['t0'], w['t1']
        if w['axis'] == 'x':
            ext = (c <= fy0 + EPS or c >= fy1 - EPS)
        else:
            ext = (c <= fx0 + EPS or c >= fx1 - EPS)
        kinds = [(kind_of or {}).get(nm, 'hab') for nm in w['rooms']]
        if len(w['rooms']) == 1:
            ext = True
        w['ext'] = ext
        if 'out' in kinds:
            w['thick'] = 0.09
        elif 'water' in kinds or 'plant' in kinds:
            w['thick'] = 0.10
        elif ext:
            w['thick'] = 0.30
        else:
            w['thick'] = 0.15
        w['openings'] = []
        L = b - a
        mid = (a + b) / 2
        if ext and L > 1.6:
            gl = [n for n in w['rooms'] if (kind_of or {}).get(n, 'hab') in ('hab', 'spec')]
            if gl:
                ww = min(3.2, L - 0.6)
                if ww > 0.7:
                    if any(k in ('living', 'dining', 'family') for k in kinds):
                        sill, head, kind = 0.05, 2.60, 'sldoor'
                    elif any(k in ('bath', 'wc', 'ensuite', 'kids_bath', 'bath2')
                             for k in kinds):
                        sill, head, kind = 1.40, 2.45, 'window'
                    elif any(k in ('bedroom', 'bedroom2', 'bedroom3', 'kids_a',
                                   'kids_b', 'kids_c', 'dress') for k in kinds):
                        sill, head, kind = 0.75, 2.45, 'window'
                    else:
                        sill, head, kind = 0.95, 2.55, 'window'
                    w['openings'].append((mid - ww / 2, mid + ww / 2, sill, head, kind))
            elif L > 3.0:
                hw = min(2.6, L - 0.8) / 2
                w['openings'].append((mid - hw, mid + hw, 0.05, 2.60, 'sldoor'))
        if not ext and L > 1.4:
            if any(k == 'circ' for k in kinds):
                w['openings'].append((mid - 0.5, mid + 0.5, 0.0, 2.10, 'door'))
    for (axis, coord, cpos, wd, kind) in doors:
        for w in walls:
            if w['axis'] == axis and abs(w['coord'] - coord) < EPS \
               and cpos - wd / 2 >= w['t0'] - EPS and cpos + wd / 2 <= w['t1'] + EPS:
                w['openings'].append((cpos - wd / 2, cpos + wd / 2, 0.0,
                                      2.15 if kind == 'door' else 2.60, kind))
                w['explicit'] = True
    return walls


def consolidate(walls, EPS=EPS):
    """Flatten overlapping walls that share a plane into disjoint segments."""
    planes = {}
    for w in walls:
        planes.setdefault((w['axis'], round(w['coord'], 3)), []).append(w)
    out = []
    for (axis, coord), group in planes.items():
        cuts = set()
        for w in group:
            cuts.add(round(w['t0'], 3))
            cuts.add(round(w['t1'], 3))
        cuts = sorted(cuts)
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a <= EPS:
                continue
            mid = (a + b) / 2
            covering = [w for w in group
                        if w['t0'] - EPS <= mid <= w['t1'] + EPS]
            if not covering:
                continue
            best = max(covering, key=lambda w: (round(w['thick'], 3),
                                                bool(w.get('ext')),
                                                len(w['rooms'])))
            seg = dict(best)
            seg['t0'], seg['t1'] = a, b
            rooms = []
            for w in covering:
                for nm in w['rooms']:
                    if nm not in rooms:
                        rooms.append(nm)
            seg['rooms'] = tuple(rooms)
            raw = []
            for w in covering:
                for o in w['openings']:
                    o0, o1 = max(o[0], a), min(o[1], b)
                    if o1 - o0 > EPS:
                        raw.append((o0, o1, o[2], o[3],
                                    o[4] if len(o) > 4 else 'window'))
            raw.sort()
            ops = []
            for o in raw:
                if ops and o[0] <= ops[-1][1] + EPS:
                    p = ops[-1]
                    ops[-1] = (p[0], max(p[1], o[1]), min(p[2], o[2]),
                               max(p[3], o[3]), p[4])
                else:
                    ops.append(o)
            ops = [o for o in ops if o[1] - o[0] >= 0.45]
            seg['openings'] = ops
            out.append(seg)
    return out


def level_walls(S, lv):
    """Consolidated walls for one scheme level."""
    return consolidate(derive(lv['rooms'], S['footprint'], lv.get('doors', ()),
                              S['kind_of']))


def gross_area(S, lv):
    fx0, fy0, fx1, fy1 = S['footprint']
    fp_area = (fx1 - fx0) * (fy1 - fy0)
    return fp_area - sum((x1 - x0) * (y1 - y0) for _, x0, y0, x1, y1, k
                         in lv['rooms'] if k in ('out', 'plant'))


def net_area(S, lv):
    fx0, fy0, fx1, fy1 = S['footprint']
    usable = (fx1 - fx0) * (fy1 - fy0)
    for _, x0, y0, x1, y1, k in lv['rooms']:
        if k in ('out', 'plant'):
            usable -= (x1 - x0) * (y1 - y0)
    return usable


def schedule(S, lv):
    """[(name, kind, area_m2)] for every room on the level."""
    out = []
    seen = {}
    for nm, x0, y0, x1, y1, k in lv['rooms']:
        a = (x1 - x0) * (y1 - y0)
        if nm in seen:
            seen[nm][1] += a
        else:
            seen[nm] = [k, a]
            out.append((nm, [k, a]))
    return [(nm, v[0], v[1]) for nm, v in seen.items()]


PRETTY = {
    'garage': 'Garage', 'genkan': 'Genkan', 'hall': 'Hall', 'pantry': "Butler's Pantry",
    'store': 'Store', 'dining': 'Dining', 'drying': 'Drying Yard', 'stair': 'Stair',
    'lift': 'Lift', 'utility': 'Utility', 'terrace': 'Terrace', 'workshop': 'Workshop',
    'bedroom': 'Bedroom', 'bedroom2': 'Bedroom 2', 'bedroom3': 'Bedroom 3',
    'kids_a': "Children's Room", 'kids_b': "Children's Room 2",
    'kids_c': "Children's Room 3", 'kids_bath': "Children's Bath",
    'bath': 'Bathroom', 'wc': 'WC', 'ensuite': 'Ensuite', 'laundry': 'Laundry',
    'kitchen': 'Kitchen', 'wetkitchen': 'Wet Kitchen', 'family': 'Family Room',
    'living': 'Living Room', 'dress': 'Dressing', 'study': 'Study',
    'slot': 'Rain Garden Slot', 'altar': 'Altar Room', 'plantdeck': 'Plant Deck',
    'loggia': 'Loggia', 'roofgarden': 'Roof Garden', 'pv': 'PV Array',
    'bridge': 'Bridge', 'kids': "Children's Room",
    'larder': 'Larder / Cold Store', 'landing': 'Landing',
    'landing2': 'Landing 2', 'landing3': 'Landing 3', 'scullery': 'Scullery',
    'bath2': 'Bathroom 2',
}


def label(nm):
    if nm in PRETTY:
        return PRETTY[nm]
    s = nm.replace('_', ' ').strip()
    return s[:1].upper() + s[1:] if s else nm
