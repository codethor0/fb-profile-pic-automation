"""fb_pfp — automate Facebook profile-picture changes via your own Brave browser.

Public API:
    Settings          — typed, env-overridable configuration
    SingleFileSource  — image source that always returns one file
    DirectorySource   — image source that picks randomly or rotates (cycle)
    ImageSource       — protocol: implement this to add new sources
                        (e.g. choosing from photos already on Facebook)
    ensure_brave      — attach to / launch Brave with a debug port
    FacebookPfpAutomator — the browser automation flow
"""

from .config import Settings
from .sources import DirectorySource, ImageSource, SingleFileSource
from .browser import ensure_brave
from .automator import AutomatorError, FacebookPfpAutomator

__version__ = "1.0.0"

__all__ = [
    "Settings",
    "DirectorySource",
    "ImageSource",
    "SingleFileSource",
    "ensure_brave",
    "AutomatorError",
    "FacebookPfpAutomator",
    "__version__",
]
