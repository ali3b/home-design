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
    brief = os.path.join(root, 'Concepts and Plan', 'concept.png')
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

    # renders
    rnd = [('street', 'Street view'), ('garden', 'From the garden (DNN land, planting only)'),
           ('riverside', 'From the river end, between the boundary walls'), ('carport', 'Drive-through carport / service bay'), ('atrium', 'Stair atrium under the skylight'), ('aerial', 'Aerial'), ('balcony', 'Upper balcony looking north'), ('massing', 'Clay massing')]
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
            d.text((x, xy[1] + p.height + 6), os.path.basename(f)[3:-4].replace('_', ' ').title(), fill=GREY, font=font(22))
        pages.append(im)

    out = os.path.join(outdir, '%s_review.pdf' % C['key'].lower())
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=150)
    print('REVIEW_OK', out, len(pages), 'pages')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
