# fb-profile-pic-automation

Auto-change your Facebook profile picture using your already-logged-in Brave browser.

The tool drives Brave over the Chrome DevTools Protocol (localhost only), so it
uses your real session — no passwords, no exported cookies, no headless browser.

## Why it's built this way

- **Your browser, your login.** Attaching to Brave on `--remote-debugging-port=9222`
  means Facebook sees the exact session you use every day.
- **macOS-safe launch.** Brave is launched via LaunchServices (`open -na`), not as a
  child process — a child inherits macOS TCC restrictions and cannot write the
  browser profile (SingletonLock fails). If Brave is already open without the debug
  port, it is quit gracefully (Cmd+Q equivalent, tabs restore on relaunch).
- **Tight DOM scoping.** The file input is only ever touched *inside* the
  "Choose profile picture" dialog — a page-wide `input[type=file]` on Facebook can
  belong to the newsfeed post composer, and uploading there would attach your image
  to a *post draft*.
- **Text-pattern selectors.** Visible labels ("Choose profile picture", "Save"),
  never generated class names, so Facebook A/B tests don't break it.
- **Human-like pacing.** Every pause is randomized; timing never looks like a
  fixed robot loop.
- **English UI.** Brave is launched with `--lang=en-US` so Facebook renders English.

## Install

```bash
pip install -r requirements.txt   # playwright only; no browser download needed
```

Requires macOS with Brave at the default location (override with
`FB_PFP_BRAVE_BINARY` / `FB_PFP_BRAVE_PROFILE`).

## Usage

```bash
python3 fb_change_pfp.py --dir ~/Pictures/pfp            # pick an image at random
python3 fb_change_pfp.py --dir ~/Pictures/pfp --cycle    # rotate, no repeats until all used
python3 fb_change_pfp.py --file ~/Pictures/pfp/me.jpg    # one specific image
python3 fb_change_pfp.py --dir ~/Pictures/pfp --dry-run  # upload but stop before Save
python3 fb_change_pfp.py -v ...                          # debug logging
```

Or the one-command wrapper (uses `$PICS_DIR`, defaults to `~/Downloads`):

```bash
./run.sh
```

### Configuration

CLI args override `FB_PFP_*` environment variables, which override defaults:

| Env var | Meaning | Default |
|---|---|---|
| `FB_PFP_DIR` | Candidate image directory | `./profile_pics` |
| `FB_PFP_FILE` | Specific image file | — |
| `FB_PFP_BRAVE_BINARY` | Brave executable | `/Applications/.../Brave Browser` |
| `FB_PFP_BRAVE_PROFILE` | Brave profile dir | `~/Library/Application Support/BraveSoftware/Brave-Browser` |
| `FB_PFP_DEBUG_PORT` | CDP port | `9222` |
| `FB_PFP_LOCALE` | Browser/UI language | `en-US` |
| `FB_PFP_STATE_FILE` | `--cycle` rotation state | `.fb_pfp_state.json` |
| `FB_PFP_SCREENSHOT_DIR` | Debug screenshots | `.` |

## Scheduling

Point `PICS_DIR` at a folder of pictures and schedule `run.sh` via cron or launchd.
Caveat: if Brave is open without the debug port at run time, it restarts (graceful
quit + session restore). Keeping Brave launched with the debug port avoids that:

```bash
open -na "Brave Browser" --args --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/BraveSoftware/Brave-Browser" \
  --lang=en-US --no-first-run
```

## Extending: new image sources

The automator only asks an `ImageSource` for a path — where it comes from is
pluggable. Implement one method:

```python
from fb_pfp import ImageSource

class FacebookAlbumSource:
    """Future idea: pick from photos already uploaded to Facebook
    instead of uploading a new file."""

    def pick(self) -> Path: ...
```

Local directory (random or no-repeat rotation) and single-file sources ship
built-in. `DirectorySource` rotation state is written atomically (temp file +
rename), so an interrupted run can never corrupt it.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest        # fully offline — no browser needed
```

Debug screenshots (`step1_loaded.png`, `step3_uploaded.png`, `after_save.png`,
`failure_state.png`) land in `FB_PFP_SCREENSHOT_DIR`.

## Security

See [SECURITY.md](SECURITY.md). Short version: the tool handles no credentials
at all, and the debug port must stay localhost-only. Automating Facebook may
violate Meta's ToS — provided for educational/personal use on accounts you own.

## License

[MIT](LICENSE)
