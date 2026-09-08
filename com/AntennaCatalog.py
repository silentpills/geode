#!/usr/bin/env python
"""Register antenna/radome identities without importing calibration values."""

import argparse
from pathlib import Path

from geode.metadata.antenna_catalog import (
    normalize_pair,
    parse_antex_pairs,
    register_pairs,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print normalized pairs without connecting to the database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser(
        "add", help="Register an explicitly chosen antenna/radome combination."
    )
    add.add_argument("antenna")
    add.add_argument("radome", help="Explicit radome code; NONE means no radome.")
    atx = commands.add_parser(
        "import-antex", help="Register receiver combinations from an ANTEX 1.4 file."
    )
    atx.add_argument("file")
    args = parser.parse_args()
    try:
        pairs = (
            [normalize_pair(args.antenna, args.radome)]
            if args.command == "add"
            else parse_antex_pairs(args.file)
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        for antenna, radome in pairs:
            print(f"{antenna} {radome}")
        return

    from geode import dbConnection
    from geode.config import get_gnss_data_cfg_path

    config_path = Path(get_gnss_data_cfg_path())
    cnn = dbConnection.Cnn(str(config_path) if config_path.is_file() else None)
    try:
        added = register_pairs(cnn.cnn, pairs)
    finally:
        cnn.cnn.close()
    print(
        f"Registered {added} new combination(s); {len(pairs) - added} already existed."
    )
    print(
        "Registration does not establish calibration availability or add height conversions."
    )


if __name__ == "__main__":
    main()
