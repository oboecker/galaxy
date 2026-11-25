"""Write what the star-system map draws (galaxy.systemmap) for the
build: public/galaxy/systems.json, and nebulae.json beside it
(the skies' nebulae).

    uv run python cli/system_maps.py [--galaxy PATH] [--out PATH]
"""

import argparse
from pathlib import Path

from galaxy import catalogue, project, systemmap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the catalogue (default: the project's)")
    parser.add_argument("--out", type=Path, help="default: systems.json in the project's public folder")
    args = parser.parse_args()
    here = project.from_args(args)
    args.out = args.out or here.public / "systems.json"
    doc = catalogue.read(here, args.galaxy)
    systemmap.write(doc, args.out)
    # The skies' nebulae, beside it.
    systemmap.write_nebulae(doc, args.out.with_name("nebulae.json"))
    print(f"  → {args.out}")


if __name__ == "__main__":
    main()
