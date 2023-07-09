# Written by Sharkus

from argparse import ArgumentParser, FileType
from pathlib import Path
import re
import sys

VER = "0.0.2"


def clean_mod(mod, no_sig):
    expr = r'( {400}.*?[^\\](?="))'
    if no_sig:
        sub = ""
    else:
        sub = f"\\\\n-- Virus cleaned by ttscleaner v{VER}\\\\n"

    (cmod, i) = re.subn(expr, sub, mod, flags=re.MULTILINE)

    print(f"Cleaned {i} infected objects")
    return cmod, i


def scan_mod(mod_path):
    from ttsmutility.parse.ModParser import ModParser, INFECTION_URL

    mod_parser = ModParser(mod_path)
    i = 0
    for trail, url in mod_parser.urls_from_mod():
        if url == INFECTION_URL:
            i += 1
            print(f"Virus detected: {'->'.join(trail)}")
    print(f"Detected {i} infected objects")


if __name__ == "__main__":
    # Create the parser object.
    parser = ArgumentParser(
        prog="ttscleaner",
        description="ttscleaner - Tabletop Simulator mod virus removal tool",
        epilog=f"{VER}",
    )

    parser.add_argument(
        "-v",
        "--version",
        help="Show version information.",
        action="version",
        version=f"%(prog)s {VER}",
    )

    parser.add_argument(
        "-s",
        "--scan",
        help="Scan and print virus info",
        dest="scan",
        action="store_true",
    )

    parser.add_argument(
        "--no-sig",
        help="Do not add signature in place of virus",
        dest="no_sig",
        action="store_true",
    )

    parser.add_argument("mod_path")

    # Finally, parse the command line.
    args = parser.parse_args()

    if not Path(args.mod_path).exists():
        print(f"'{args.mod_path}' not found!")
        sys.exit(-11)

    if args.scan:
        print(f"Scanning mod '{args.mod_path}'")
        scan_mod(args.mod_path)
    else:
        print(f"Cleaning mod '{args.mod_path}'")
        with open(args.mod_path, "r", encoding="utf-8") as f:
            mod = f.read()

        cleaned, i = clean_mod(mod, args.no_sig)
        if i > 0:
            dest_path = Path(args.mod_path).with_suffix(".cleaned")
            print(f"Saving cleaned mod to '{dest_path}'")
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(cleaned)
