"""Plan generation engine.

A scheme is authored as per-level cell grids (cols x rows), each cell mapped to
a room name. From that single source we derive:
  * wall segments (with thickness), doors, windows
  * room polygons, labels, area schedule
  * the wall/opening lists consumed by the Blender scene builder
so the drawings and the 3D renders can never disagree.
"""
import math

# ------------------------------------------------------------------ site ----
PLOT_W, PLOT_D = 13.5, 65.0
HX0, HX1 = 1.50, 13.20          # house west/east faces (concept 1)
HY0, HY1 = 0.00, 19.80          # house south/north faces (19.8 m deep)
LANE_X = (0.0, 1.50)            # 1.5 m west service passage
Z_ROAD = 0.00
Z_GF = 0.60                     # finished ground floor, given
Z_F1 = 3.90
Z_F2 = 7.00
Z_PARAPET = 9.90

# room programme -> (fill, hatch, label colour hint)
KIND = {
    'hab':    ('#f6f2ea', 'none',  'HABITABLE'),
    'serv':   ('#e7e9e6', 'tile',  'SERVICE / WET'),
    'circ':   ('#efece4', 'none',  'CIRCULATION'),
    'out':    ('#dfe4d6', 'deck',  'OUTDOOR'),
    'water':  ('#cfe0e2', 'none',  'WATER'),
    'store':  ('#ece5d6', 'none',  'STORAGE'),
    'spec':   ('#e9dfd6', 'none',  'SPECIAL'),
    'plant':  ('#dde3cf', 'leaf',  'PLANT / VOID'),
}

WALL_T_EXT = 0.30
WALL_T_INT = 0.15
WALL_T_WC = 0.12
WALL_T_GLASS = 0.08


def R(x0, y0, x1, y1):
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def area(r):
    return (r[2] - r[0]) * (r[3] - r[1])


class Level:
    """cols/rows are ordered lists of grid line coordinates (metres).

    cells: dict (ci, ri) -> room name.  Room kind comes from NAMES.
    void:  set of cells with no building above/below (open court, light slot)
    open_edges: set of ((ci,ri),'N'|'S'|'E'|'W') - no wall on this cell edge
    doors:  list of ((ci,ri), edge, width_m)  edge = side of that cell
    """

    def __init__(self, name, z, ztop, cols, rows, cells, kind_of,
                 void=None, open_edges=None, doors=None, storeys=None):
        self.name = name
        self.z = z
        self.ztop = ztop
        self.cols = cols
        self.rows = rows
        self.cells = cells
        self.kind_of = kind_of
        self.void = void or set()
        self.open_edges = open_edges or set()
        self.doors = doors or []
        self.storeys = storeys


class Scheme:
    def __init__(self, key, title, tagline, levels, site, massing, meta):
        self.key = key
        self.title = title
        self.tagline = tagline
        self.levels = levels
        self.site = site
        self.massing = massing
        self.meta = meta


# ------------------------------------------------------------- derivation ---

def cell_rect(lv, ci, ri):
    return R(lv.cols[ci], lv.rows[ri], lv.cols[ci + 1], lv.rows[ri + 1])


def rooms(lv):
    """name -> list of rects (one per cell)"""
    out = {}
    for (ci, ri), nm in lv.cells.items():
        out.setdefault(nm, []).append(cell_rect(lv, ci, ri))
    return out


def schedule(lv):
    """[(name, kind, m2)] sorted by area desc"""
    rs = rooms(lv)
    rows = [(nm, lv.kind_of[nm], sum(area(r) for r in rects))
            for nm, rects in rs.items()]
    rows.sort(key=lambda t: -t[2])
    return rows


def is_void(lv, ci, ri):
    return (ci, ri) in lv.void


def walls(lv, boundary_x0=None, boundary_x1=None, boundary_y0=None, boundary_y1=None):
    """Return list of wall dicts, deduplicated.

    Each wall: dict(a=(x,y), b=(x,y), t=thickness, ext=bool, rooms=(n1,n2),
                    axis='x'|'y', openings=[dict(s, w, sill, head, kind)])
    """
    bx0 = HX0 if boundary_x0 is None else boundary_x0
    bx1 = HX1 if boundary_x1 is None else boundary_x1
    by0 = HY0 if boundary_y0 is None else boundary_y0
    by1 = HY1 if boundary_y1 is None else boundary_y1
    nc, nr = len(lv.cols) - 1, len(lv.rows) - 1
    seen = {}
    door_edges = {(c, e): w for (c, e), w in
                  (((c, side), w) for (c, side, w) in lv.doors)}

    def nb(ci, ri, side):
        if side == 'S':
            return (ci, ri - 1)
        if side == 'N':
            return (ci, ri + 1)
        if side == 'W':
            return (ci - 1, ri)
        return (ci + 1, ri)

    for (ci, ri), nm in sorted(lv.cells.items()):
        if is_void(lv, ci, ri):
            continue
        r = cell_rect(lv, ci, ri)
        x0, y0, x1, y1 = r
        edges = [
            ('S', (x0, y0), (x1, y0), 'x'),
            ('N', (x0, y1), (x1, y1), 'x'),
            ('W', (x0, y0), (x0, y1), 'y'),
            ('E', (x1, y0), (x1, y1), 'y'),
        ]
        for side, a, b, axis in edges:
            if ((ci, ri), side) in lv.open_edges:
                continue
            nci, nri = nb(ci, ri, side)
            # which grid line is this edge on?
            if side in 'SN':
                gi = lv.cols[ci] if side == 'W' else lv.cols[ci + 1]
                gj = lv.rows[ri] if side == 'S' else lv.rows[ri + 1]
            else:
                gi = lv.cols[ci] if side == 'W' else lv.cols[ci + 1]
                gj = lv.rows[ri]
            key = (axis, round(gi, 3), round(gj, 3))
            if key in seen:
                w = seen[key]
                if nm not in w['rooms']:
                    w['rooms'] = tuple(sorted(set(w['rooms'] + (nm,))))
                continue
            # exterior test
            if axis == 'x':
                ext = gj <= by0 + 1e-6 or gj >= by1 - 1e-6
            else:
                ext = gi <= bx0 + 1e-6 or gi >= bx1 - 1e-6
            if not ext:
                has = lv.cells.get((nci, nri))
                if has is None or is_void(lv, nci, nri):
                    ext = True      # faces a void: treat as glazed facade
            t = WALL_T_EXT if ext else WALL_T_INT
            kind = lv.kind_of.get(nm, 'hab')
            if kind == 'out':
                t = WALL_T_GLASS
            if kind in ('water', 'plant') and not ext:
                t = 0.0
            w = dict(a=a, b=b, t=t, ext=ext, rooms=(nm,), axis=axis, openings=[])
            seen[key] = w
    # vertical boundaries force exterior
    for w in seen.values():
        gi = w['a'][0] if w['axis'] == 'y' else w['a'][1]
        gj = w['a'][1] if w['axis'] == 'y' else w['a'][0]
        if w['axis'] == 'y' and (abs(gi - bx0) < 1e-6 or abs(gi - bx1) < 1e-6):
            w['ext'] = True
            w['t'] = max(w['t'], WALL_T_EXT)
        if w['axis'] == 'x' and (abs(gj - by0) < 1e-6 or abs(gj - by1) < 1e-6):
            w['ext'] = True
            w['t'] = max(w['t'], WALL_T_EXT)
    # doors
    for (ci, ri), side, wd in lv.doors:
        for w in seen.values():
            r = cell_rect(lv, ci, ri)
            x0, y0, x1, y1 = r
            if side == 'S' and abs(w['a'][1] - y0) < 1e-6 and \
               min(x0, w['b'][0]) < x1 - 1e-6 and max(x0, w['b'][0]) > x0 + 1e-6:
                pass
            else:
                continue
            L = w['b'][0] - w['a'][0]
            c = (w['a'][0] + w['b'][0]) / 2
            w['openings'].append(dict(s=c - wd / 2, w=wd, sill=0.0, head=2.10,
                                      kind='door', axis='x'))
    # interior doors: any wall with a 'circ' cell on one side
    for w in seen.values():
        if w['t'] == 0:
            continue
        L = abs(w['b'][0] - w['a'][0]) + abs(w['b'][1] - w['a'][1])
        if w['ext'] or L < 1.4:
            continue
        c = ((w['a'][0] + w['b'][0]) / 2, (w['a'][1] + w['b'][1]) / 2)
        w['openings'].append(dict(s=None, w=0.90, sill=0.0, head=2.10,
                                  kind='door', axis=w['axis'], mid=c, L=L))
    # windows on habitable / special external walls
    for w in seen.values():
        if not w['ext'] or w['t'] == 0:
            continue
        rm = w['rooms'][0]
        kind = lv.kind_of.get(rm, 'hab')
        if kind in ('out', 'water', 'plant', 'circ', 'serv'):
            continue
        L = abs(w['b'][0] - w['a'][0]) + abs(w['b'][1] - w['a'][1])
        if L < 1.5:
            continue
        ww = min(2.4, L - 0.9)
        w['openings'].append(dict(s=None, w=ww, sill=0.95, head=2.35,
                                  kind='window', axis=w['axis'],
                                  mid=((w['a'][0] + w['b'][0]) / 2,
                                       (w['a'][1] + w['b'][1]) / 2), L=L))
    return sorted(seen.values(), key=lambda w: (w['axis'], w['a']))


def gfa(scheme):
    """gross internal area per level (hab + serv + circ + spec + store), excl outdoor/void"""
    out = []
    for lv in scheme.levels:
        s = 0.0
        for nm, kind, a2 in schedule(lv):
            if kind in ('out', 'water', 'plant'):
                continue
            s += a2
        out.append((lv.name, s))
    return out


def footprint_area(scheme):
    return (HX1 - HX0) * (HY1 - HY0)