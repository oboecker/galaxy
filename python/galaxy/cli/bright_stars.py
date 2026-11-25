"""Take the bright stars from a HYG catalogue CSV into
galaxy/data/bright-stars.csv (galaxy.brightstars) — once, or again after a
change of the selection; the catalogue itself is not kept here.

    uv run python cli/bright_stars.py HYG.csv
"""

import argparse
import csv
from pathlib import Path

from galaxy import brightstars


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("hyg", type=Path, help="the HYG catalogue, v1 columns (StarID, HIP, …, ProperName, RA, Dec, Distance, Mag, Spectrum)")
    args = parser.parse_args()
    with args.hyg.open(encoding="utf-8") as f:
        stars = brightstars.extract(csv.DictReader(f))
    out = Path(brightstars.__file__).parent / brightstars.DATA
    out.write_text(brightstars.write(stars), encoding="utf-8")
    print(f"  → {out}: {len(stars)} stars, {len({s['system'] for s in stars})} systems")


if __name__ == "__main__":
    main()
