# Architecture

The code is small and split so that everything except the browser steps can be tested without a browser.

| Module | Role |
|---|---|
| `src/fb_pfp/cli.py` | Parses arguments, sets up logging, wires the pieces together, returns the exit status |
| `src/fb_pfp/config.py` | `Settings`, built from defaults, `FB_PFP_*` variables and command-line options, in that order of increasing priority |
| `src/fb_pfp/sources.py` | Image sources: `SingleFileSource`, `DirectorySource`, and the `ImageSource` protocol |
| `src/fb_pfp/browser.py` | Attaches to Brave, or quits and relaunches it with the debug port |
| `src/fb_pfp/automator.py` | The Facebook steps, driven through Playwright |
| `fb_change_pfp.py` | Thin wrapper so `python3 fb_change_pfp.py` works without installing the package |

Playwright is imported only when a run starts, so importing the package and running the unit tests do not need it.

## Rules the code follows

- Subprocesses use fixed argument lists. No shell strings, no `eval`.
- Input from the command line and environment is checked before it reaches the file system or the browser.
- Errors are raised as typed exceptions and end in a non-zero exit status. Nothing is swallowed without a log line.
- State is written to a temporary file and renamed, under a file lock, so an interrupted or concurrent run cannot corrupt it.
- Every wait has a timeout.
- The file input is looked up inside the profile picture dialog only. A page-wide file input on Facebook can belong to the post composer.
- The browser connection is never closed. Only the tab this tool opened is closed, because closing the connection would end your whole Brave session.
- Randomness is passed in (`rng`), so tests can make it predictable.

## Adding an image source

An image source answers one question: which picture should be used now? Implement `pick()`. If your source keeps state, also implement `record_success()`, which is called only after Facebook accepted the picture.

```python
from pathlib import Path

from fb_pfp import FacebookPfpAutomator, Settings, ensure_brave
from fb_pfp.sources import RecordsSuccess


class NewestFileSource:
    """Always use the most recently modified image in a folder."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def pick(self) -> Path:
        files = [p for p in self._folder.iterdir() if p.suffix.lower() in {".jpg", ".png"}]
        return max(files, key=lambda p: p.stat().st_mtime)


source = NewestFileSource(Path("~/Pictures/profile-pics").expanduser())
image = source.pick()
settings = Settings(source_kind="file", image_file=image)
ensure_brave(settings)
FacebookPfpAutomator(settings).run(image)
if isinstance(source, RecordsSuccess):
    source.record_success(image)
```

The command-line tool only knows the built-in sources. To expose a new one as a command-line option, add it in `cli.py` and add tests for it.
