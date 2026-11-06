#!/usr/bin/env python3
"""Package the shaded Vial master artwork into all native icon formats."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def main():
    icons = ROOT / 'src/main/icons'
    # The SVG embeds the untouched original artwork and a color-only filter.
    # Its rendered PNG is checked in: normal builds need no SVG renderer/browser.
    with Image.open(ROOT / 'util/packaging/vi_al_logo.png') as image:
        master = image.convert('RGBA')
        for folder, sizes in {'base': (16, 24, 32, 48, 64),
                              'linux': (128, 256, 512, 1024),
                              'mac': (128, 256, 512, 1024)}.items():
            for size in sizes:
                master.resize((size, size), Image.Resampling.LANCZOS).save(icons / folder / f'{size}.png')
        master.save(icons / 'Icon.ico', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
        master.save(icons / 'Icon.icns')
    print('Updated PNG, ICO and ICNS icons from the original shaded purple artwork.')


if __name__ == '__main__':
    main()
