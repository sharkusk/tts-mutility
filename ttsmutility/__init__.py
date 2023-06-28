"""A terminal-based Markdown document viewer, written in Textual."""
from importlib.metadata import version, PackageNotFoundError

__author__ = "Marcus Kellerman"
__copyright__ = "Marcus Kellerman"
__credits__ = ["Marcus Kellerman", "Dave Pearson", "eigengrau"]
__maintainer__ = "Marcus Kellerman"
__email__ = ""
__licence__ = "GPLv3"

try:
    __version__ = version("ttsmutility")
except PackageNotFoundError:
    # package is not installed
    pass
