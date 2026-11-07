"""Load a concept JSON + site JSON into the scheme dict used by lib/sheetgen and the Blender builder."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(concept_path, site_path=None):
    with open(concept_path) as f:
        C = json.load(f)
    site_path = site_path or os.path.join(os.path.dirname(os.path.abspath(concept_path)), 'site.json')
    with open(site_path) as f:
        site = json.load(f)
    site = dict(site)
    site['trees'] = [(x, y) for x, y, kind in C.get('planting_dnn', []) if kind == 'tree']
    levels = []
    kind_of = {}
    for lv in C['levels']:
        L = dict(lv)
        L['rooms'] = [tuple(r) for r in lv['rooms']]
        L['doors'] = [tuple(d) for d in lv.get('doors', [])]
        L['facade_rules'] = C.get('facade_rules', {})
        L['style'] = C.get('style', {})
        L['footprint'] = C['footprint']
        for r in L['rooms']:
            kind_of.setdefault(r[0], r[5])
        levels.append(L)
    roofs = C.get('roofs', [])
    S = dict(
        key=C['key'], title=C['title'], tagline=C.get('tagline', ''), idea=C.get('idea', ''),
        footprint=tuple(C['footprint']), kind_of=kind_of, levels=levels, site=site,
        massing=dict(roofs=[r for r in roofs if r.get('kind', 'hip') in ('hip', 'gable', 'flat')], fascia=[]), section_cut=C.get('section_cut', 7.0),
        storeys=len(levels), concept=C,
        site_notes=[], index_notes=[
            'Concept fitted wholly inside the ONT road-side band. The DNN land is shown '
            'as existing garden and planting only.'],
        schedule_notes=[],
    )
    # west strip (service passage / carport) for the site plan
    from lib import sheetgen
    sp = C.get('service_passage', [0.0, 1.5])
    sheetgen.LANE_X = (sp[0], sp[1])
    S['passage_label'] = C.get('passage_label') or ('CARPORT /\nSERVICE BAY' if C.get('carport') else 'SERVICE\nPASSAGE')
    if C.get('drawing_extent'):
        sheetgen.HX0, sheetgen.HX1 = C['drawing_extent']
    extra = [r for r in roofs if r.get('kind') in ('skylight', 'lean')]
    if extra:
        S['index_notes'].append('Also shown in the 3D model but not on the roof plan: ' + ', '.join(
            'central skylight lantern' if r['kind'] == 'skylight' else 'lean-to carport roof' for r in extra) + '.')
    # labels for the drawing engine
    from lib import rectwalls
    rectwalls.PRETTY.update(C.get('labels', {}))
    return S


def install_walls():
    """Route the drawing engine's wall derivation through walls2 (open plan aware)."""
    from lib import rectwalls, walls2, sheetgen
    rectwalls.level_walls = walls2.level_walls
    sheetgen.level_walls = walls2.level_walls
