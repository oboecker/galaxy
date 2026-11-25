"""Write the catalogue's layers merged into one file, the whole catalogue
other readers take, and each layer as its own file, which the galaxy map
loads (galaxy.catalogue).

    python -m galaxy.cli.catalogue --project PATH --out public/galaxy.json --layers public/layers
"""

import argparse
from pathlib import Path

from galaxy import catalogue, project
from galaxy.fs import write_atomic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the project's own layer (default: the project's catalogue)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--layers", type=Path, help="also write each layer as <name>.json into this folder")
    args = parser.parse_args()
    here = project.from_args(args)
    write_atomic(args.out, catalogue.text(here, args.galaxy))
    print(f"  → {args.out}")
    if args.layers:
        for path in catalogue.write_layers(args.layers, here):
            print(f"  → {path}")


if __name__ == "__main__":
    main()
