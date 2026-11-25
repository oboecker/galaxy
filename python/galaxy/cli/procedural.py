"""The procedural galaxy (galaxy.procedural): measure the catalogue into
the project's procedural.json, or write the layer, the maps' bundle or the
galaxy's light.

    uv run python cli/procedural.py --measure          # the numbers, again (moves every system)
    uv run python cli/procedural.py [--within LY] --out PATH     # the layer's dots
    uv run python cli/procedural.py --bundle DIR       # what the maps load (the build)
    uv run python cli/procedural.py --glow PATH        # the galaxy's light, for the skies' band
"""

import argparse
import json
from pathlib import Path

from galaxy import catalogue, jsonstore, procedural, project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--measure", action="store_true",
                        help="measure the catalogue into the project's procedural.json: every procedural system moves")
    parser.add_argument("--seed", type=int, default=1, help="with --measure")
    parser.add_argument("--within", type=float, help="only the disc this many light years round Sol")
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the catalogue (default: the project's)")
    parser.add_argument("--out", type=Path, help="where the layer's dots go")
    parser.add_argument("--bundle", type=Path, help="write the maps' files into this directory (public/galaxy)")
    parser.add_argument("--glow", type=Path, help="write the galaxy's light (the skies' band) to this file")
    args = parser.parse_args()
    here = project.from_args(args)
    if args.glow:
        args.glow.parent.mkdir(parents=True, exist_ok=True)
        args.glow.write_text(json.dumps(procedural.glow(procedural.load()), separators=(",", ":")) + "\n",
                             encoding="utf-8")
        print(f"  → {args.glow}")
        return
    doc = catalogue.read(here, args.galaxy)
    if args.measure:
        model = procedural.measure(doc, args.seed)
        here.procedural.write_text(jsonstore.dumps(model), encoding="utf-8")
        print(f"  → {here.procedural}: {model['density'] * 1e6:.2f} systems per 1,000 ly² round Sol")
        return
    if args.bundle:
        made = procedural.bundle(args.bundle, doc)
        print(f"  → {args.bundle}: {made['systems']} procedural systems, {made['links']} gate links")
        return
    if not args.out:
        parser.error("the layer needs --out")
    dots = procedural.layer(procedural.load(), doc, args.within)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dots, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  → {args.out}: {len(dots)} systems, nearest neighbour {procedural.nearest_spacing(dots):.0f} ly (median)")


if __name__ == "__main__":
    main()
