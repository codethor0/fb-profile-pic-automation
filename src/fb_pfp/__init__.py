"""fb_pfp: change a Facebook profile picture through your own Brave browser.

Public API:
    Settings             typed configuration (CLI args, FB_PFP_* variables, defaults)
    SingleFileSource     image source that always returns one file
    DirectorySource      image source that picks at random or rotates through a folder
    ImageSource          protocol to implement for a new kind of image source
    ensure_brave         attach to Brave, launching it with a debug port if needed
    FacebookPfpAutomator the browser automation flow
"""

from .config import Settings
from .sources import DirectorySource, ImageSource, SingleFileSource
from .browser import ensure_brave
from .automator import AutomatorError, FacebookPfpAutomator

__version__ = "1.0.3"

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
