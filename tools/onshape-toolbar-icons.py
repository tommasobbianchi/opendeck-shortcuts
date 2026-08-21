#!/usr/bin/env python3
"""Cut Onshape's sketch toolbar into per-tool icons for the deck.

Onshape's help site names an icon inside each tool's own page, which works for the solid
features and not at all for the sketch tools: `fillettooliconLG.png` does not exist, `line.htm`
is a different topic entirely, and the site's search index is a stub. The toolbar itself is the
authoritative picture, so this takes a screenshot of it and cuts it up.

The boxes below were measured against a 1284x35 capture of the sketch toolbar taken on
2026-08-21. A different window width or zoom moves them, so `--verify` writes a labelled
contact sheet: look at it before trusting the result, because a mislabelled crop puts an equals
sign on the key marked Perpendicular and nothing complains.

Output goes to the app-art directory, not the icon cache: these are Onshape's drawings, used
for Onshape's own tools, and never uploaded anywhere.

The capture itself is not in this repository for the same reason -- a screenshot of Onshape's
toolbar is Onshape's art, and this repository is public. Keep yours outside the tree and pass
its path; `~/Schermate/` is where they land on this fleet.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortcuts import icons  # noqa: E402
from shortcuts.model import Shortcut  # noqa: E402

#: tool name -> (x0, x1) in the reference capture. The strip is 35px tall, so y is the whole of it.
BOXES = {
    "line": (0, 32), "corner_rectangle": (56, 77), "circle": (108, 129), "arc": (160, 181),
    "polygon": (212, 233), "spline": (264, 285), "point": (316, 336), "text": (349, 372),
    "use": (386, 403), "dimension": (437, 456), "fillet": (474, 494), "trim": (527, 546),
    "offset": (580, 597), "mirror": (630, 651), "pattern": (665, 684), "dxf": (717, 736),
    "transform": (773, 793), "coincident": (810, 831), "concentric": (845, 864),
    "parallel": (878, 898), "tangent": (912, 933), "horizontal": (947, 966),
    "vertical": (986, 995), "perpendicular": (1014, 1035), "equal": (1052, 1065),
    "midpoint": (1082, 1103),
}

#: Which catalogue action each toolbar icon belongs to. One drawing can serve two actions:
#: Onshape shows a single rectangle icon and hides centre-rectangle behind its dropdown.
ACTIONS = {
    "line": ["line"],
    "corner_rectangle": ["corner_rectangle", "center_rectangle"],
    "circle": ["circle"],
    "arc": ["arc"],
    "point": ["sketch_point"],
    "use": ["use"],
    "dimension": ["dimension"],
    "trim": ["trim"],
    "offset": ["offset"],
    "coincident": ["coincident"],
    "concentric": ["concentric"],
    "parallel": ["parallel"],
    "tangent": ["tangent"],
    "horizontal": ["horizontal"],
    "vertical": ["vertical"],
    "perpendicular": ["perpendicular"],
    "equal": ["equal"],
    "midpoint": ["midpoint"],
    "mirror": ["mirror"],
    "pattern": ["pattern"],
    "transform": ["transform"],
    "polygon": ["polygon"],
    "spline": ["spline"],
    "text": ["text"],
    "fillet": ["sketch_fillet"],
}

SIZE = 96
BACKGROUND = (0, 0, 0)


def crop(image, box, size=SIZE):
    """One icon, centred on black at the deck's key size."""
    from PIL import Image

    x0, x1 = box
    glyph = image.crop((x0, 0, x1 + 1, image.height)).convert("RGBA")
    # The capture carries the toolbar's own grey behind every icon; on a key that reads as a
    # grey tile floating on black. Drop it, so the drawing sits on the key's background.
    pixels = glyph.load()
    for y in range(glyph.height):
        for x in range(glyph.width):
            r, g, b, a = pixels[x, y]
            if abs(r - 51) <= 12 and abs(g - 51) <= 12 and abs(b - 51) <= 12:
                pixels[x, y] = (0, 0, 0, 0)
    # trim fully transparent/empty margins so the drawing fills the key
    bbox = glyph.getbbox()
    if bbox:
        glyph = glyph.crop(bbox)
    scale = min((size - 12) / glyph.width, (size - 12) / glyph.height)
    glyph = glyph.resize((max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))),
                         Image.LANCZOS)
    key = Image.new("RGB", (size, size), BACKGROUND)
    key.paste(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2), glyph)
    return key


def main() -> int:
    from PIL import Image, ImageDraw

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", help="a capture of Onshape's sketch toolbar, 1284x35")
    parser.add_argument("--app", default="onshape", help="identity segment the icons belong to")
    parser.add_argument("--verify", metavar="PNG", help="write a labelled contact sheet and stop")
    args = parser.parse_args()

    image = Image.open(args.screenshot)
    if image.size != (1284, 35):
        print(f"warning: boxes were measured on 1284x35, this is {image.size[0]}x{image.size[1]}; "
              "check --verify before believing any of it", file=sys.stderr)

    if args.verify:
        cell, cols = 60, 9
        rows = (len(BOXES) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (cell + 12) + 12, rows * (cell + 24) + 12), (28, 28, 28))
        draw = ImageDraw.Draw(sheet)
        for i, (name, box) in enumerate(BOXES.items()):
            glyph = crop(image, box, cell)
            x = 12 + (i % cols) * (cell + 12)
            y = 12 + (i // cols) * (cell + 24)
            sheet.paste(glyph, (x, y))
            draw.text((x, y + cell + 3), name[:12], fill=(190, 190, 190))
        sheet.save(args.verify)
        print(f"wrote {args.verify} -- look at it")
        return 0

    written = 0
    for name, actions in ACTIONS.items():
        if name not in BOXES:
            continue
        glyph = crop(image, BOXES[name])
        for action in actions:
            shortcut = Shortcut(id=f"{args.app}.{action}", app=args.app, label=action,
                                combo="a", provenance="extracted", source=args.screenshot)
            path = icons.app_art_path(shortcut)
            path.parent.mkdir(parents=True, exist_ok=True)
            glyph.save(path)
            print(f"{shortcut.id}\t{path}")
            written += 1
    print(f"{written} icon(s) into {icons.app_art_dir()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
