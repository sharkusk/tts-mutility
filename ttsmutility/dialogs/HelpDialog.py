"""The main help dialog for the application."""

import webbrowser

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown
from typing_extensions import Final

from .. import __version__
from ..utility.advertising import APPLICATION_TITLE

HELP: Final[
    str
] = f"""\
# {APPLICATION_TITLE} v{__version__} Help

Welcome to {APPLICATION_TITLE} Help! {APPLICATION_TITLE} was built with [Textual](https://github.com/Textualize/textual).

## NOTE: Keys are reliminary and may change at any time!

| Key | Navigation Command |
| -- | -- |
| `/` | Filter Game Names |
| `esc` | Close Filter Bar / Background Task Window |
| `tab` | Cycle Tabs |
| `ctrl+q` | Quit the application |

| Key | Mod Command |
| -- | -- |
| `Ctrl+d` | Download Missing Assets from Mod |
| `Ctrl+b` | Create zip backup of Mod |
| `Ctrl+r` | Force refresh Mod |

| Key | General Command |
| -- | -- |
| `F1` | This help |
| `ctrl+l` | View log |
| `ctrl+o` | Open Config |
| `ctrl+s` | Compute SHA1s |
| `ctrl+m` | Show SHA1 Mismatches |
| `ctrl+n` | Save Content Names to .csv |
| `ctrl+f` | Load Content Names from .csv |

"""
"""The main help text for the application."""


class HelpDialog(ModalScreen[None]):
    """Modal dialog that shows the application's help."""

    DEFAULT_CSS = """
    HelpDialog {
        align: center middle;
    }

    HelpDialog > Vertical {
        border: thick $primary 50%;
        width: 80%;
        height: 80%;
        background: $boost;
    }

    HelpDialog > Vertical > VerticalScroll {
        height: 1fr;
        margin: 1 2;
    }

    HelpDialog > Vertical > Center {
        padding: 1;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape,f1", "dismiss(None)", "", show=False),
    ]
    """Bindings for the help dialog."""

    def compose(self) -> ComposeResult:
        """Compose the help screen."""
        with Vertical():
            with VerticalScroll():
                yield Markdown(HELP)
            with Center():
                yield Button("Close", variant="primary")

    def on_mount(self) -> None:
        """Configure the help screen once the DOM is ready."""
        # It seems that some things inside Markdown can still grab focus;
        # which might not be right. Let's ensure that can't happen here.
        self.query_one(Markdown).can_focus_children = False
        self.query_one("Vertical > VerticalScroll").focus()

    def on_button_pressed(self) -> None:
        """React to button press."""
        self.dismiss(None)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """A link was clicked in the help.

        Args:
            event: The link click event to handle.
        """
        webbrowser.open(event.href)
