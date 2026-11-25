"""Write everything the maps read into one folder, with its manifest.json
(galaxy.build).

    python -m galaxy.cli.build --project PATH --out public/galaxy [--procedural [--within LY]]
"""

import argparse
from pathlib import Path

from galaxy import build, project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True, help="the folder the maps load from")
    parser.add_argument("--procedural", action="store_true", help="also the procedural galaxy (minutes)")
    parser.add_argument("--within", type=float, help="with --procedural: only this many light years round Sol")
    args = parser.parse_args()
    written = build.write(args.out, here=project.from_args(args), procedural_galaxy=args.procedural,
                          within=args.within)
    print(f"  → {args.out}: {len(written)} files and folders, manifest.json last")


if __name__ == "__main__":
    main()
