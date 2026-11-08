#!/usr/bin/env python3
"""Copy review images (resized JPEG) + the review PDF into docs/ for GitHub Pages and write docs/gallery.json.
    python3 pipeline/publish_docs.py out/c1 c1
"""
import glob
import json
import os
import shutil
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(outdir, key):
    dst = os.path.join(ROOT, 'docs', 'img', key)
    os.makedirs(dst, exist_ok=True)
    n = key[1:]
    brief = 'img/concept1.png' if key == 'c1' else 'img/concept%s.png' % n
    # a concept may have no publishable brief image (e.g. a third-party brochure): skip the tile
    items = [{'src': brief, 'caption': 'Concept %s brief image' % n}] if os.path.exists(os.path.join(ROOT, 'docs', brief)) else []
    groups = [
        ('render', ['street', 'carport', 'atrium', 'foyer', 'family', 'garden', 'riverside', 'aerial', 'balcony', 'deck', 'massing'], 'Blender · '),
        ('unity', None, 'Walkthrough · '),
        ('sheets', ['01_site', '02_plans_a', '03_roof', '04_section', '05_schedule'], 'Drawing · '),
    ]
    for sub, order, prefix in groups:
        files = [os.path.join(outdir, sub, n + '.png') for n in order] if order else sorted(glob.glob(os.path.join(outdir, sub, '*.png')))
        for f in files:
            if not os.path.exists(f):
                continue
            name = os.path.splitext(os.path.basename(f))[0]
            im = Image.open(f).convert('RGB')
            if im.width > 1800:
                im = im.resize((1800, int(im.height * 1800 / im.width)), Image.LANCZOS)
            out = os.path.join(dst, '%s_%s.jpg' % (sub, name))
            im.save(out, quality=86, optimize=True)
            label = name.split('_', 1)[-1] if sub == 'unity' else name.split('_', 1)[-1] if sub == 'sheets' else name
            cap = prefix + label.replace('_', ' ').title()
            if sub == 'unity' and label.startswith('sun_'):      # sun_winter_0900 -> Sun study · Winter solstice 09:00 (solar time)
                _, season, hhmm = label.split('_')
                cap = 'Sun study · %s solstice %s:%s (solar time)' % (season.title(), hhmm[:2], hhmm[2:])
            items.append({'src': os.path.relpath(out, os.path.join(ROOT, 'docs')), 'caption': cap})
    pdf = glob.glob(os.path.join(outdir, '*_review.pdf'))
    if pdf:
        shutil.copy(pdf[0], os.path.join(ROOT, 'docs', os.path.basename(pdf[0])))
    wt = os.path.join(outdir, 'unity', 'walktest.txt')
    if os.path.exists(wt):
        shutil.copy(wt, os.path.join(ROOT, 'docs', key + '_walktest.txt'))
    vj = os.path.join(outdir, 'validate.json')
    if os.path.exists(vj):
        shutil.copy(vj, os.path.join(ROOT, 'docs', key + '_validate.json'))
    json.dump(items, open(os.path.join(ROOT, 'docs', 'gallery.json' if key == 'c1' else 'gallery_%s.json' % key), 'w'), indent=1)
    print('PUBLISH_OK', len(items), 'images')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
