"""Fetch the SandiaDecay nuclear database used by `openrad identify`.

openrad doesn't vendor this file: it's ~6 MB of LGPL-2.1-licensed nuclear
data from Sandia National Labs (https://github.com/sandialabs/SandiaDecay),
which sits awkwardly under this project's MIT license and would bloat the
repo. Instead, fetch your own copy and point openrad at it:

    python scripts/fetch_isotope_database.py
    openrad identify some_spectrum.spe --database ~/.openrad/isotopes/sandia.decay.xml

Source data license: LGPL-2.1 (Sandia National Labs / NTESS). See
https://github.com/sandialabs/SandiaDecay/blob/master/LICENSE.txt.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from openrad.analysis.isotopes import DEFAULT_DATABASE_PATH

SOURCE_URL = (
    "https://raw.githubusercontent.com/sandialabs/SandiaDecay/master/"
    "sandia.decay.nocoinc.min.xml"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"Where to save the database (default: {DEFAULT_DATABASE_PATH})",
    )
    args = parser.parse_args()

    args.dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {SOURCE_URL}")
    urllib.request.urlretrieve(SOURCE_URL, args.dest)
    print(f"Saved to {args.dest} ({args.dest.stat().st_size / 1e6:.1f} MB)")
    print("Source: Sandia National Labs' SandiaDecay project, LGPL-2.1 license.")


if __name__ == "__main__":
    main()
