"""Piece-wise wall derivation for concept JSON levels.

Each wall plane is split at every room corner, and each piece is classified by
the rooms on its two sides. That gives:
  * open-plan: no wall between two rooms in the level's `open` list
  * one auto window per room facade (not one per merged plane)
  * railings (not walls) around outdoor rooms, glazing around light courts
Output matches lib/rectwalls wall dicts so lib/sheetgen draws the same plan
the Blender/Unity model is built from.

Convention (as rectwalls): axis='x' -> wall RUNS along x at constant y=coord.
"""
EPS = 0.02
T_EXT, T_INT, T_GLASS, T_RAIL = 0.25, 0.12, 0.08, 0.06


def _room_at(rooms, x, y):
    for r in rooms:
        nm, x0, y0, x1, y1, k = r
        if x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6:
            return r
    return None


def derive(lv, kind_of=None):
    rooms = lv['rooms']
    open_ = set(lv.get('open', ()))
    planes = {}
    for nm, x0, y0, x1, y1, k in rooms:
        for c, a, b in ((y0, x0, x1), (y1, x0, x1)):
            planes.setdefault(('x', round(c, 3)), set()).update((round(a, 3), round(b, 3)))
        for c, a, b in ((x0, y0, y1), (x1, y0, y1)):
            planes.setdefault(('y', round(c, 3)), set()).update((round(a, 3), round(b, 3)))
    pieces = []
    for (axis, c), cuts in planes.items():
        cuts = sorted(cuts)
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a < EPS:
                continue
            m = (a + b) / 2
            if axis == 'x':
                r1, r2 = _room_at(rooms, m, c - 0.05), _room_at(rooms, m, c + 0.05)
            else:
                r1, r2 = _room_at(rooms, c - 0.05, m), _room_at(rooms, c + 0.05, m)
            if r1 is None and r2 is None:
                continue
            if r1 is not None and r2 is not None and r1[0] == r2[0]:
                continue
            if r1 and r2 and r1[0] in open_ and r2[0] in open_:
                continue
            sides = [r for r in (r1, r2) if r]
            kinds = [r[5] for r in sides]
            ext = len(sides) == 1
            if all(k == 'out' for k in kinds):
                typ, t = 'rail', T_RAIL
            elif 'out' in kinds and 'plant' in kinds:
                typ, t = 'rail', T_RAIL
            elif 'plant' in kinds:
                typ, t = 'glass', T_GLASS
            else:
                typ, t = 'solid', (T_EXT if ext else T_INT)
            pieces.append(dict(axis=axis, coord=c, t0=a, t1=b, rooms=tuple(r[0] for r in sides),
                               kinds=tuple(kinds), ext=ext, type=typ, thick=t,
                               side=(1 if (ext and r2 is None) else -1 if ext else 0),
                               openings=[]))
    # explicit doors
    for axis, coord, pos, wd, kind in lv.get('doors', ()):
        o0, o1 = pos - wd / 2, pos + wd / 2
        hit = False
        for p in pieces:
            if p['axis'] == axis and abs(p['coord'] - coord) < EPS and p['t0'] < o1 - EPS and p['t1'] > o0 + EPS:
                p['openings'].append((max(o0, p['t0']), min(o1, p['t1']), 0.0,
                                      2.15 if kind == 'door' else 2.55, kind))
                p['explicit'] = True
                hit = True
        if not hit:
            print('walls2: door matched no wall', axis, coord, pos)
    # auto windows on external solid pieces, one per room facade
    ground = lv.get('z', 0) < 1.0
    for p in pieces:
        if not p['ext'] or p['type'] != 'solid' or p.get('explicit'):
            continue
        L = p['t1'] - p['t0']
        nm, k = p['rooms'][0], p['kinds'][0]
        mid = (p['t0'] + p['t1']) / 2
        north = p['axis'] == 'x' and p['side'] == 1 and p['coord'] > 15
        if k in ('hab', 'spec'):
            if L < 1.4:
                continue
            if north and ground:
                ww = min(3.6, L - 0.9)
                p['openings'].append((mid - ww / 2, mid + ww / 2, 0.0, 2.55, 'sldoor'))
            else:
                ww = min(2.4, L - 0.9)
                p['openings'].append((mid - ww / 2, mid + ww / 2, 0.75, 2.45, 'window'))
        elif k in ('serv', 'store'):
            if L >= 1.6:
                ww = min(1.2, L - 0.8)
                p['openings'].append((mid - ww / 2, mid + ww / 2, 1.45, 2.35, 'window'))
        elif k == 'circ' and L >= 1.8:
            ww = min(1.6, L - 0.8)
            p['openings'].append((mid - ww / 2, mid + ww / 2, 0.9, 2.45, 'window'))
    return pieces


def level_walls(S, lv):
    return derive(lv, S.get('kind_of'))
