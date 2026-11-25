"""Write the public maps site's data (galaxy.public): the allowed fields of
galaxy.json, the system maps, the travel colours and the planet maps.

    uv run python cli/public_maps.py --project path/to/project.toml --out maps-site/public/data
"""

import argparse
from pathlib import Path

from galaxy import project, public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="a directory, emptied first")
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the catalogue (default: the project's)")
    parser.add_argument("--travel", type=Path, help="travel.json (default: the project's)")
    parser.add_argument("--planets", type=Path,
                        help="where the build put the planet maps' textures (default: the project's)")
    parser.add_argument("--no-procedural", action="store_true", help="without the procedural galaxy (three minutes)")
    args = parser.parse_args()
    project.from_args(args)
    written = public.bundle(args.out, galaxy_json=args.galaxy, travel_json=args.travel, planets=args.planets,
                            with_procedural=not args.no_procedural)
    print(f"  → {args.out}: {len(written)} files")


if __name__ == "__main__":
    main()
