#!/usr/bin/env python3
"""Constraint checker for a concept JSON against concepts/site.json.

    python3 pipeline/validate.py concepts/c1_courtyard_house.json [--json out.json]

Hard rules (from the owner's property pack):
  * every structure (rooms, slabs, roof incl. overhang, porch, balcony, fence) lies in the ONT band
  * nothing is built in the DNN band (planting is allowed)
Also checks: rooms inside footprint, no overlapping rooms, every door hits a wall.
Exit 1 on any breach.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scheme import load  # noqa: E402
from lib import walls2  # noqa: E402

TOL = 0.005


def main(argv):
    path = argv[0]
    S = load(path)
    C, site = S['concept'], S['site']
    W = site['site']['width']
    ont = site['bands']['ONT']
    errors, warns, report = [], [], {}

    def inside_ont(name, x0, y0, x1, y1, boundary_ok=False):
        lo = -0.2 if boundary_ok else 0.0
        if x0 < lo - TOL or x1 > W - lo + TOL or y0 < ont['y0'] + lo - TOL or y1 > ont['y1'] + TOL:
            errors.append('%s (%.2f,%.2f)-(%.2f,%.2f) is outside the ONT band x 0–%.2f, y %.2f–%.2f'
                          % (name, x0, y0, x1, y1, W, ont['y0'], ont['y1']))

    fx0, fy0, fx1, fy1 = S['footprint']
    inside_ont('house footprint', fx0, fy0, fx1, fy1)
    for r in C.get('roofs', []):
        o = r.get('overhang', 0)
        inside_ont('roof (incl. %.2f m overhang)' % o, r['x0'] - o, r['y0'] - o, r['x1'] + o, r['y1'] + o)
    p = C.get('porch')
    if p:
        inside_ont('porch', p['x0'], p['y0'], p['x1'], p['y1'])
    f = C.get('fence', {})
    if 'front' in f:
        inside_ont('front fence', 0, f['front']['y'] - 0.12, W, f['front']['y'] + 0.12, boundary_ok=True)
    if 'sides' in f:
        inside_ont('side fences', 0, 0, W, f['sides']['y1'], boundary_ok=True)
    for extra in C.get('structures', []):
        inside_ont(extra.get('name', 'structure'), *extra['rect'])

    for lv in S['levels']:
        rs = lv['rooms']
        for nm, x0, y0, x1, y1, k in rs:
            inside_ont('%s/%s' % (lv['short'], nm), x0, y0, x1, y1)
            if x0 < fx0 - TOL or y0 < fy0 - TOL or x1 > fx1 + TOL or y1 > fy1 + TOL:
                errors.append('%s/%s is outside the footprint' % (lv['short'], nm))
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                ox = min(a[3], b[3]) - max(a[1], b[1])
                oy = min(a[4], b[4]) - max(a[2], b[2])
                if ox > TOL and oy > TOL:
                    errors.append('%s: rooms %s and %s overlap' % (lv['short'], a[0], b[0]))
        area_rooms = sum((x1 - x0) * (y1 - y0) for _, x0, y0, x1, y1, _k in rs)
        fp_area = (fx1 - fx0) * (fy1 - fy0)
        if abs(area_rooms - fp_area) > 0.05:
            warns.append('%s: rooms cover %.1f m² of the %.1f m² footprint' % (lv['short'], area_rooms, fp_area))
        gfa = sum((x1 - x0) * (y1 - y0) for _, x0, y0, x1, y1, k in rs if k not in ('out', 'plant'))
        outdoor = sum((x1 - x0) * (y1 - y0) for _, x0, y0, x1, y1, k in rs if k == 'out')
        report[lv['short']] = dict(gfa=round(gfa, 1), outdoor=round(outdoor, 1))
        pieces = walls2.derive(lv)
        for d in lv['doors']:
            axis, coord, pos, wd, kind = d
            if not any(p['axis'] == axis and abs(p['coord'] - coord) < 0.02 and p['t0'] < pos < p['t1'] for p in pieces):
                errors.append('%s: door %s does not land on a wall' % (lv['short'], list(d)))

    # DNN: nothing but planting
    dnn = site['bands']['DNN']
    for x, y, kind in C.get('planting_dnn', []):
        if kind not in ('tree', 'shrub', 'grass', 'hedge'):
            errors.append('DNN item %s at (%.1f,%.1f) is not planting' % (kind, x, y))
        if not (dnn['y0'] <= y <= dnn['y1']):
            warns.append('planting_dnn item at y=%.1f is not in DNN' % y)

    fp_area = (fx1 - fx0) * (fy1 - fy0)
    ont_area = W * (ont['y1'] - ont['y0'])
    report['footprint_m2'] = round(fp_area, 1)
    report['ont_coverage_pct'] = round(100 * fp_area / ont_area, 1)
    report['total_gfa_m2'] = round(sum(v['gfa'] for k, v in report.items() if isinstance(v, dict)), 1)
    report['errors'], report['warnings'] = errors, warns
    print('Concept %s — %s' % (C['key'], C['title']))
    for k, v in report.items():
        if k not in ('errors', 'warnings'):
            print('  %-18s %s' % (k, v))
    for w in warns:
        print('  WARN  ', w)
    for e in errors:
        print('  BREACH', e)
    print('VALIDATE_OK' if not errors else 'VALIDATE_FAIL')
    if '--json' in argv:
        with open(argv[argv.index('--json') + 1], 'w') as fh:
            json.dump(report, fh, indent=1)
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
