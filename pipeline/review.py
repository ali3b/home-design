#!/usr/bin/env python3
"""Assemble the concept review PDF from sheets, Blender renders and Unity walkthrough shots.
    python3 pipeline/review.py concepts/c1_courtyard_house.json out/c1
"""
import glob
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 2480, 1754          # A3 landscape @ 150 dpi
M = 70
INK, GREY, RED, PAPER = (36, 31, 26), (110, 103, 92), (168, 64, 40), (252, 250, 245)


def font(size, bold=False):
    for p in (['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'] if bold else []) + \
             ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def page(title, sub=''):
    im = Image.new('RGB', (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.text((M, 40), title, fill=INK, font=font(46, True))
    if sub:
        d.text((M, 100), sub, fill=GREY, font=font(26))
    d.text((M, H - 50), 'CONCEPT ONLY — NOT FOR CONSTRUCTION · subject to survey, legal merger, setbacks and permits',
           fill=RED, font=font(22))
    return im, d


def fit(img, box):
    x, y, w, h = box
    im = Image.open(img).convert('RGB') if isinstance(img, str) else img
    r = min(w / im.width, h / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    return im, (x + (w - im.width) // 2, y + (h - im.height) // 2)


def wrap(d, text, xy, width, f, fill=INK, lh=1.35):
    x, y = xy
    line = ''
    for w in text.split():
        t = (line + ' ' + w).strip()
        if d.textlength(t, font=f) > width:
            d.text((x, y), line, fill=fill, font=f)
            y += int(f.size * lh)
            line = w
        else:
            line = t
    if line:
        d.text((x, y), line, fill=fill, font=f)
        y += int(f.size * lh)
    return y


NAVY, PALE, SEASON_COL = (24, 38, 82), (205, 200, 190), [(96, 128, 168), (120, 160, 96), (214, 140, 50), (176, 104, 70)]


def mvnd(v):
    return '%.0f M VND' % (v / 1e6) if abs(v) >= 1e6 else '%.0f VND' % v


def solar_page(C, outdir):
    """Rooftop solar: panel plan, energy per season/month, indicative economics (from pipeline/solar.py)."""
    sj = os.path.join(outdir, 'solar.json')
    if not os.path.exists(sj):
        return None
    R = json.load(open(sj))
    site = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'concepts', 'site.json')))
    rec, A = R['recommended'], R['assumptions']
    im, d = page('Rooftop solar — energy per season',
                 '%d × %s panels = %.1f kWp on the roof · latitude %s · %s · shaded by the assumed 3-storey neighbours'
                 % (rec['panels'], A['module'].split(',')[0], rec['kwp'], A['latitude'], A['weather']))
    # ---- roof plan (left)
    S, ox, oy = 46, M + 90, 1160            # px per metre; origin = site SW corner
    T = lambda x, y: (ox + x * S, oy - y * S)
    for n in site.get('neighbours', []):
        d.rectangle([T(max(n['x0'], -1.6), n['y1']), T(min(n['x1'], 15.1), n['y0'])], fill=(232, 228, 220), outline=GREY)
        d.text(T(max(n['x0'], -1.6) + 0.1, n['y1'] - 0.3), '3-storey\nneighbour\n11.2 m\n(assumed)', fill=GREY, font=font(17))
    d.rectangle([T(0, 19.73), T(13.5, 0)], outline=RED, width=2)
    d.text(T(0.1, 19.73 + 0.55), 'ONT band 13.5 × 19.73 m — road at the bottom', fill=RED, font=font(18))
    for r in C['roofs']:
        o = r.get('overhang', 0) if r.get('kind', 'hip') in ('hip', 'gable', 'flat') else 0
        d.rectangle([T(r['x0'] - o, r['y1'] + o), T(r['x1'] + o, r['y0'] - o)], outline=INK, width=2)
    for p in R['panels']:
        pts = [T(*c[:2]) for c in p['corners']]
        d.polygon(pts, fill=NAVY if p['keep'] else PALE, outline=PAPER)
        if not p['keep']:
            cx = sum(q[0] for q in pts) / 4; cy = sum(q[1] for q in pts) / 4
            t = str(p['kwh_per_kwp']); d.text((cx - d.textlength(t, font=font(14)) / 2, cy - 8), t, fill=GREY, font=font(14))
    # north arrow and scale
    ax, ay = T(16.4, 3.5)
    d.polygon([(ax, ay - 50), (ax - 14, ay), (ax + 14, ay)], fill=INK); d.text((ax - 8, ay - 82), 'N', fill=INK, font=font(24, True))
    sx, sy = T(9.5, -0.9)
    d.line([sx, sy, sx + 5 * S, sy], fill=INK, width=4); d.text((sx, sy + 6), '5 m', fill=INK, font=font(18))
    ly = oy + 90
    d.rectangle([M, ly, M + 30, ly + 22], fill=NAVY); d.text((M + 40, ly), 'Recommended panels', fill=INK, font=font(20))
    d.rectangle([M + 330, ly, M + 360, ly + 22], fill=PALE)
    d.text((M + 370, ly), 'Fit but not worth it: number = kWh per kWp a year (an unshaded ideal panel gives %d)'
           % A['reference_kwh_per_kwp'], fill=INK, font=font(20))
    # surface table
    y = ly + 50
    cols = [M, M + 420, M + 600, M + 760, M + 900]
    for x, t in zip(cols, ['Roof surface', 'Tilt / faces', 'Fit / used', 'kWh/kWp', 'no neighbours']):
        d.text((x, y), t, fill=INK, font=font(19, True))
    y += 30
    for b in R['surfaces']:
        az = {0: 'N', 90: 'E', 180: 'S', 270: 'W'}.get(b['azimuth'], str(b['azimuth']))
        for x, t in zip(cols, [b['surface'], '%d° %s' % (b['tilt'], az), '%d / %d' % (b['panels'], b['kept']),
                               str(b['kwh_per_kwp']), str(b['kwh_per_kwp_no_neighbours'])]):
            d.text((x, y), t, fill=GREY, font=font(19))
        y += 27
    # ---- seasons (right)
    X = 1330
    d.text((X, 170), 'ENERGY FROM THE RECOMMENDED ARRAY', fill=INK, font=font(28, True))
    y = 220
    for x, t in zip((X, X + 200, X + 400, X + 600, X + 820), ('Season', 'Months', 'kWh', 'kWh / day', 'Share')):
        d.text((x, y), t, fill=INK, font=font(22, True))
    y += 38
    for i, s in enumerate(rec['seasons']):
        d.rectangle([X - 22, y + 4, X - 8, y + 22], fill=SEASON_COL[i])
        for x, t in zip((X, X + 200, X + 400, X + 600, X + 820), (s['season'], s['months'], '{:,}'.format(s['kwh']),
                        '%.1f' % s['kwh_per_day'], '%d %%' % round(100 * s['kwh'] / rec['year_kwh']))):
            d.text((x, y), t, fill=INK, font=font(24))
        y += 38
    d.line([X, y, X + 1000, y], fill=GREY, width=1); y += 8
    for x, t in zip((X, X + 400, X + 600), ('Year', '{:,}'.format(rec['year_kwh']), '%.1f' % (rec['year_kwh'] / 365))):
        d.text((x, y), t, fill=INK, font=font(24, True))
    y += 44
    y = wrap(d, 'Without the assumed neighbours the same panels would give {:,} kWh a year ({:+.0f} %). All {} panels that '
             'physically fit would give {:,} kWh, but the extra ones are on shaded or east/west/north slopes.'.format(
                 rec['year_kwh_no_neighbours'], 100 * (rec['year_kwh_no_neighbours'] / rec['year_kwh'] - 1),
                 R['all_that_fit']['panels'], R['all_that_fit']['year_kwh']), (X, y), 1040, font(20), GREY)
    # monthly bars
    y += 16
    bh, bw, top = 230, 70, y + 10
    mx = max(rec['monthly_kwh'])
    season_of = {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}
    for m, v in enumerate(rec['monthly_kwh']):
        h = bh * v / mx
        x0 = X + m * (bw + 16)
        d.rectangle([x0, top + bh - h, x0 + bw, top + bh], fill=SEASON_COL[season_of[m + 1]])
        t = '{:,}'.format(v); d.text((x0 + bw / 2 - d.textlength(t, font=font(16)) / 2, top + bh - h - 22), t, fill=INK, font=font(16))
        d.text((x0 + bw / 2 - 8, top + bh + 6), 'JFMAMJJASOND'[m], fill=GREY, font=font(18))
    y = top + bh + 40
    # economics
    E = R['economics']
    d.text((X, y), 'IS IT WORTH IT? (indicative)', fill=INK, font=font(28, True)); y += 46
    b = E.get('best_size'); r_ = E['recommended']
    cols = (X, X + 470, X + 790)
    d.text((cols[1], y), 'Recommended', fill=INK, font=font(21, True))
    d.text((cols[2], y), 'Best-value size', fill=INK, font=font(21, True)); y += 30
    rows = [('Panels / kWp', '%d / %.1f' % (rec['panels'], rec['kwp']), '%d / %.1f' % (b['panels'], b['kwp'])),
            ('Installed cost', mvnd(r_['cost']), mvnd(b['cost'])),
            ('Bill saving, first year', mvnd(r_['saving_year1']), mvnd(b['saving_year1'])),
            ('Output used in the house', '%d %%' % r_['self_use_pct'], '%d %%' % b['self_use_pct']),
            ('Share of the bill-kWh covered', '%d %%' % r_['covers_pct'], '%d %%' % b['covers_pct']),
            ('Simple payback', ('%.0f years' % r_['payback_years']) if r_['payback_years'] else 'over 25 years',
             ('%.0f years' % b['payback_years']) if b['payback_years'] else 'over 25 years'),
            ('Net over 25 years', mvnd(r_['net_25y']), mvnd(b['net_25y']))]
    for k, v1, v2 in rows:
        d.text((cols[0], y), k, fill=INK, font=font(21)); d.text((cols[1], y), v1, fill=INK, font=font(21))
        d.text((cols[2], y), v2, fill=INK, font=font(21)); y += 30
    a = E['assumptions']
    y += 8
    wrap(d, 'Assumes: an example air-conditioned family using about {:,} kWh a year (bill {} a year), EVN household tiers '
         'from 1 Nov 2026 + {:.0f} % VAT, {} per kWp installed, nothing paid for power sent to the grid (the buy-back '
         'rate is not yet published), 0.5 %/yr panel ageing, 1 %/yr upkeep. Surplus power is the limit: the house uses '
         'most of its power in the evening. Try other numbers at ali3b.github.io/home-design/solar.html.'.format(
             sum(a['load_monthly']), mvnd(r_['bill_before']), a['vat'] * 100, mvnd(a['cost_per_kwp'])),
         (X, y), 1040, font(19), GREY)
    return im


def battery_page(C, outdir):
    """Batteries (grid-connected) and the off-grid test, from solar.json['batteries']."""
    sj = os.path.join(outdir, 'solar.json')
    if not os.path.exists(sj):
        return None
    R = json.load(open(sj))
    Bt = R.get('batteries')
    if not Bt:
        return None
    im, d = page('Batteries and living off-grid',
                 'Hour-by-hour over a typical year · battery %s per usable kWh incl. hybrid inverter, replaced once (year 13, 60 %%) '
                 '· nothing paid for surplus power' % mvnd(Bt['battery_cost_per_kwh']))
    seas = ['Winter', 'Spring', 'Summer', 'Autumn']

    def bars(x, y, sp):
        for i, k in enumerate(seas):
            v = sp[k]
            d.rectangle([x + i * 52, y + 26 - 24 * v / 100, x + i * 52 + 40, y + 26], fill=SEASON_COL[i])
            d.text((x + i * 52, y + 28), '%d' % v, fill=GREY, font=font(15))

    cols = [M, M + 160, M + 300, M + 480, M + 790, M + 940, M + 1140, M + 1310]
    heads = ['Panels', 'Battery', 'Cost', 'From sun: W Sp Su Au', 'Year', 'No-grid days', 'Saving / yr', 'Payback']
    y = 165
    for hk in ('no_ac', 'ac'):
        H_ = Bt['households'][hk]
        d.text((M, y), '%s — example household using about %s kWh a year (bill %s a year)' % (
            H_['label'].upper(), '{:,}'.format(H_['year_kwh']), mvnd(H_['grid_tied'][0]['bill_before'])), fill=INK, font=font(26, True))
        y += 44
        for x, t in zip(cols, heads):
            d.text((x, y), t, fill=INK, font=font(19, True))
        d.text((M + 1470, y), 'Net over 25 years', fill=INK, font=font(19, True))
        y += 30
        best = max(H_['grid_tied'], key=lambda c: c['net_25y'])
        for c in H_['grid_tied']:
            hl = c is best
            if hl:
                d.rectangle([M - 12, y - 6, W - M, y + 46], fill=(240, 232, 214))
            f = font(21, hl)
            vals = ['%d (%.1f kWp)' % (c['panels'], c['kwp']), 'none' if not c['battery_kwh'] else '%d kWh' % c['battery_kwh'],
                    mvnd(c['cost']), None, '%d %%' % c['sun_share_pct'], str(c['grid_free_days']), mvnd(c['saving_year1']),
                    ('%.0f yrs' % c['payback_years']) if c['payback_years'] else '> 25 yrs']
            for x, t in zip(cols, vals):
                if t is None:
                    bars(x, y - 4, c['seasons_pct'])
                else:
                    d.text((x, y + 6), t, fill=INK, font=f)
            d.text((M + 1470, y + 6), mvnd(c['net_25y']) + ('   ← best value' if hl else ''), fill=RED if hl else INK, font=f)
            y += 52
        y += 18
    # off-grid verdicts
    d.text((M, y), 'CAN THE HOUSE LIVE OFF-GRID?', fill=INK, font=font(28, True)); y += 46
    for hk in ('no_ac', 'ac'):
        H_ = Bt['households'][hk]
        ok = [c for c in H_['off_grid'] if c['grid_kwh'] == 0]
        if ok:
            c = min(ok, key=lambda c: c['cost'])
            v = ('%s: YES in a typical year with %d panels (%.1f kWp%s) and a %d kWh battery, about %s. That costs %s more over '
                 '25 years than staying on the grid.' % (H_['label'], c['panels'], c['kwp'],
                                                        ', every panel that fits, including the shaded slopes' if c['array'] != 'recommended' else '',
                                                        c['battery_kwh'], mvnd(c['cost']), mvnd(-c['net_25y'])))
        else:
            c = max(H_['off_grid'], key=lambda c: (c['sun_share_pct'], -c['cost']))
            v = ('%s: NOT on this roof. The best tested (%d panels, %d kWh battery, %s) runs %d %% of the year\'s power from the sun, '
                 'but still needs %s kWh from a generator or the grid, with up to %d days in a row short.' % (
                     H_['label'], c['panels'], c['battery_kwh'], mvnd(c['cost']), c['sun_share_pct'],
                     '{:,}'.format(c['grid_kwh']), c['longest_short_run_days']))
        y = wrap(d, v, (M, y), W - 2 * M, font(23), INK) + 6
        near = [c for c in H_['off_grid'] if 0 < c['grid_kwh'] <= 60]
        if near:
            c = min(near, key=lambda c: c['cost'])
            y = wrap(d, '   Nearly: %d panels with %d kWh covers all but %d kWh a year (%d short days, the worst needing %.1f kWh).'
                     % (c['panels'], c['battery_kwh'], c['grid_kwh'], 365 - c['grid_free_days'], c['worst_day_grid_kwh']),
                     (M, y), W - 2 * M, font(21), GREY) + 4
    y += 8
    wrap(d, 'A "typical year" leaves out the worst years. Northern winters bring weeks of drizzle and low cloud, so an off-grid house '
         'needs a margin: about 30 % more battery and panels, or a small generator for bad spells. Off-grid also wastes the summer surplus. '
         'Staying connected with a 5–10 kWh battery gets most of the benefit for far less money, and keeps the lights on in power cuts.',
         (M, y), W - 2 * M, font(20), GREY)
    return im


def main(concept, outdir):
    C = json.load(open(concept))
    here = os.path.dirname(os.path.abspath(__file__))
    vj = os.path.join(outdir, 'validate.json')
    subprocess.run([sys.executable, os.path.join(here, 'validate.py'), concept, '--json', vj], capture_output=True)
    rep = json.load(open(vj))
    pages = []

    # cover
    im, d = page(C['title'], C.get('tagline', ''))
    root = os.path.dirname(os.path.dirname(os.path.abspath(concept)))
    brief = os.path.join(root, 'Concepts and Plan', 'concept.png') if C['key'] == 'C1' else ''
    if C.get('brief'):
        # publishable copy with the header (place names) cropped off
        brief = os.path.join(root, C['brief']['published'])
    street = os.path.join(outdir, 'render', 'street.png')
    if os.path.exists(street):
        p, xy = fit(street, (M, 170, 1460, 900)); im.paste(p, xy)
        d.text((M, 1080), 'Blender render — street view (golden hour)', fill=GREY, font=font(22))
    if os.path.exists(brief):
        p, xy = fit(brief, (1580, 170, 830, 560)); im.paste(p, xy)
        d.text((1580, 740), 'Concept %s brief image (inspiration)' % C['key'][1:], fill=GREY, font=font(22))
    elif os.path.exists(os.path.join(outdir, 'render', 'aerial.png')):
        p, xy = fit(os.path.join(outdir, 'render', 'aerial.png'), (1580, 170, 830, 560)); im.paste(p, xy)
        d.text((1580, 740), 'Blender render — aerial from the south-west', fill=GREY, font=font(22))
    y = 800
    d.text((1580, y), 'THE CONCEPT IN NUMBERS', fill=INK, font=font(28, True)); y += 46
    rows = [('Footprint', '%.1f m²  (%.0f%% of ONT band)' % (rep['footprint_m2'], rep['ont_coverage_pct'])),
            ('Ground floor', '%.0f m² enclosed' % rep['Ground']['gfa']),
            ('Upper floor', '%.0f m² enclosed + %.0f m² balcony' % (rep['Upper']['gfa'], rep['Upper']['outdoor'])),
            ('Total enclosed', '%.0f m²' % rep['total_gfa_m2']),
            ('Constraint check', 'PASS — all structures in ONT; DNN planting only' if not rep['errors'] else 'FAIL')]
    for k, v in rows:
        d.text((1580, y), k, fill=INK, font=font(24, True)); d.text((1840, y), v, fill=GREY, font=font(24)); y += 40
    y += 20
    y = wrap(d, C.get('idea', ''), (M, 1130), 1460, font(25))
    y = 1130
    wt = os.path.join(outdir, 'unity', 'walktest.txt')
    if os.path.exists(wt):
        last = [l for l in open(wt).read().splitlines() if 'rooms reachable' in l]
        d.text((1580, 1130), 'Walkthrough test: ' + (last[0] if last else ''), fill=INK, font=font(24, True))
    note = C.get('review_note') or ('The concept image asked for about 230–250 m² on the ground floor. The ONT band is only about 266 m², '
            'so the plan is fitted inside it with a 1.5 m west service passage, a 2.4 m forecourt and 0.6 m eaves. '
            'That gives ' + '%.0f m²' % rep['Ground']['gfa'] + ' enclosed on the ground floor. '
            'The house sits on the east boundary, which needs a boundary/setback check.')
    wrap(d, note, (1580, 1180), 830, font(22), GREY)
    pages.append(im)

    # drawing sheets
    for f in sorted(glob.glob(os.path.join(outdir, 'sheets', '0*.png'))):
        if f.endswith('00_index.png'):
            continue
        im = Image.open(f).convert('RGB').resize((W, H), Image.LANCZOS)
        pages.append(im)

    sp = solar_page(C, outdir)
    if sp:
        pages.append(sp)
    bp = battery_page(C, outdir)
    if bp:
        pages.append(bp)

    # renders
    rnd = [('street', 'Street view'), ('garden', 'From the garden (DNN land, planting only)'),
           ('riverside', 'From the river end, between the boundary walls'), ('carport', 'Drive-through carport / service bay'), ('atrium', 'Stair atrium under the skylight'), ('foyer', 'Foyer looking down the hall to the living area'), ('family', 'Family, meals and kitchen opening to the alfresco'), ('aerial', 'Aerial'), ('balcony', 'Upper balcony looking north'), ('deck', 'Covered deck on the garage roof'), ('massing', 'Clay massing')]
    have = [(os.path.join(outdir, 'render', k + '.png'), t) for k, t in rnd if os.path.exists(os.path.join(outdir, 'render', k + '.png'))]
    for i in range(0, len(have), 2):
        im, d = page('Blender views', 'Cycles renders from the same data as the drawings and the walkthrough')
        for j, (f, t) in enumerate(have[i:i + 2]):
            p, xy = fit(f, (M + j * 1190, 170, 1150, 1400)); im.paste(p, xy)
            d.text((M + j * 1190, xy[1] + p.height + 12), t, fill=GREY, font=font(24))
        pages.append(im)

    # unity shots, 4 per page
    shots = sorted(glob.glob(os.path.join(outdir, 'unity', '*.png')))
    for i in range(0, len(shots), 4):
        im, d = page('Walkthrough (Unity)', 'Interactive model: these are fixed viewpoints you can jump to with keys 1–9')
        for j, f in enumerate(shots[i:i + 4]):
            x, y = M + (j % 2) * 1190, 160 + (j // 2) * 770
            p, xy = fit(f, (x, y, 1150, 710)); im.paste(p, xy)
            lab = os.path.basename(f)[3:-4]
            if lab.startswith('sun_'):
                _, season, hhmm = lab.split('_')
                lab = 'Sun study: %s solstice, %s:%s solar time' % (season, hhmm[:2], hhmm[2:])
            d.text((x, xy[1] + p.height + 6), lab.replace('_', ' ')[:1].upper() + lab.replace('_', ' ')[1:] if lab.startswith('Sun') else lab.replace('_', ' ').title(), fill=GREY, font=font(22))
        pages.append(im)

    out = os.path.join(outdir, '%s_review.pdf' % C['key'].lower())
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=150)
    print('REVIEW_OK', out, len(pages), 'pages')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
