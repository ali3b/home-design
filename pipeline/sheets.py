#!/usr/bin/env python3
"""Drawing sheets (site, plans, roof, section, schedule, cover) for a concept JSON.
    python3 pipeline/sheets.py concepts/c1_courtyard_house.json out/c1/sheets [--dpi 150]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scheme import load, install_walls
from lib import sheetgen

def main(argv):
    S = load(argv[0]); install_walls()
    dpi = int(argv[argv.index('--dpi') + 1]) if '--dpi' in argv else 150
    for f in sheetgen.render(S, argv[1], dpi):
        print('sheet:', f)
    print('SHEETS_OK')

if __name__ == '__main__':
    main(sys.argv[1:])
