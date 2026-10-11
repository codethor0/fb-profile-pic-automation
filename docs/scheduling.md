# Running on a schedule

`run.sh` picks the next image from `PICS_DIR` (in `--cycle` mode) and sets it as your profile picture. Make sure `PICS_DIR` holds only pictures you are happy to make public.

Do a manual run first, and check that it works with your Brave and your Facebook login:

```bash
PICS_DIR=~/Pictures/profile-pics ./run.sh
```

## Choose the Python

`run.sh` uses `python3` from the `PATH`. A scheduled job has a short `PATH`, so point it at the Python that has Playwright installed. If you installed into `.venv` as described in the README, set `FB_PFP_PYTHON` to that interpreter, for example `/Users/you/fb-profile-pic-automation/.venv/bin/python`.

## launchd (recommended on macOS)

Save this as `~/Library/LaunchAgents/com.codethor0.fb-pfp.plist`. Replace `you` and the paths with your own. This example runs every day at 09:15.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.codethor0.fb-pfp</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/you/fb-profile-pic-automation/run.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PICS_DIR</key>
    <string>/Users/you/Pictures/profile-pics</string>
    <key>FB_PFP_PYTHON</key>
    <string>/Users/you/fb-profile-pic-automation/.venv/bin/python</string>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/you/.fb_pfp/run.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/you/.fb_pfp/run.log</string>
</dict>
</plist>
```

Create the log folder, then load the job:

```bash
mkdir -p ~/.fb_pfp
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codethor0.fb-pfp.plist
```

Run it once now to test it, and check the log:

```bash
launchctl kickstart -k gui/$(id -u)/com.codethor0.fb-pfp
tail -n 20 ~/.fb_pfp/run.log
```

Remove it:

```bash
launchctl bootout gui/$(id -u)/com.codethor0.fb-pfp
```

## cron

```cron
15 9 * * * PICS_DIR=$HOME/Pictures/profile-pics FB_PFP_PYTHON=$HOME/fb-profile-pic-automation/.venv/bin/python /bin/bash $HOME/fb-profile-pic-automation/run.sh >> $HOME/.fb_pfp/run.log 2>&1
```

cron on macOS may need Full Disk Access, and it only works while you are logged in with Brave available. launchd is the better fit.

## Things to know

- Your Mac must be awake and you must be logged in. The job needs your Brave profile and its Facebook login.
- If Brave is already open without the debug port, the job quits it and starts it again. See the README for the risk.
- A run that fails does not use up an image in `--cycle` mode.
- Very regular automated activity may be treated differently by Facebook than a person changing a picture now and then. A weekly or irregular schedule is gentler.
