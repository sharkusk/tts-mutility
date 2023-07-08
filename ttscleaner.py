# Written by Sharkus

from argparse import ArgumentParser, FileType
from pathlib import Path
import re
import sys

VER = "0.0.1"

def clean_mod(mod):
    expr = r'( {400}.*?[^\\](?="))'
    sub = f"\\\\n-- Virus cleaned by ttscleaner v{VER}\\\\n"

    (cmod, i) = re.subn(expr, sub, mod, flags=re.MULTILINE)

    print(f"Cleaned {i} infected objects")
    return cmod, i

if __name__ == "__main__":

    # Create the parser object.
    parser = ArgumentParser(
        prog="ttscleaner",
        description="ttscleaner - Tabletop Simulator mod virus removal tool",
        epilog=f"{VER}",
    )

    # Add --version
    parser.add_argument(
        "-v",
        "--version",
        help="Show version information.",
        action="version",
        version=f"%(prog)s {VER}",
    )

    parser.add_argument("mod_path")

    # Finally, parse the command line.
    args = parser.parse_args()

    if not Path(args.mod_path).exists():
        print(f"'{args.mod_path}' not found!")
        sys.exit(-11)
    
    print(f"Cleaning mod '{args.mod_path}'")
    with open(args.mod_path, "r", encoding="utf-8") as f:
        mod = f.read()

    cleaned, i = clean_mod(mod)
    if i > 0:
        with open(Path(args.mod_path).with_suffix(".cleaned"), "w", encoding="utf-8") as f:
            f.write(cleaned)
    