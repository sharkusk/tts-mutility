"""Provides the 'branding' for the application."""

from typing_extensions import Final
from .. import __version__

ORGANISATION_NAME: Final[str] = "sharkusk"
"""The organisation name to use when creating namespaced resources."""

ORGANISATION_TITLE: Final[str] = "Sharkusk"
"""The organisation title."""

ORGANISATION_URL: Final[str] = "https://github.com/sharkusk"
"""The organisation URL."""

PACKAGE_NAME: Final[str] = "ttsmutility"
"""The name of the package."""

APPLICATION_TITLE: Final[str] = "TTSMutility"
"""The title of the application."""

USER_AGENT: Final[str] = f"{PACKAGE_NAME} v{__version__}"
"""The user agent to use when making web requests."""

DISCORD: Final[str] = "https://discord.gg/Enf6Z3qhVr"
"""The link to the Textualize Discord server."""

TEXTUAL_URL: Final[str] = "https://textual.textualize.io/"
"""The URL people should visit to find out more about Textual."""
