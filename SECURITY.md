# Security policy

## Reporting a vulnerability

Please report security problems privately through a
[GitHub security advisory](https://github.com/codethor0/fb-profile-pic-automation/security/advisories/new).
Do not open a public issue for a security report.

Include what you found, the steps to reproduce it, and the version (`fb-pfp --version`).
This is a one-person project. I aim to reply within a week.

## Supported versions

Only the latest release receives fixes.

## What the tool does and does not handle

- It does not read, store or send passwords, cookies or tokens.
- It talks to your own Brave browser over the DevTools Protocol on `localhost`, and to Facebook through that browser.
- It starts a few local programs with fixed argument lists (`open`, `osascript`, `pgrep`, `pkill`). It never builds a shell command from input.
- It reads one folder of images you choose and writes only to its own state folder.

## The open debug port

While Brave runs with `--remote-debugging-port`, any program on your Mac can connect to it and control the browser, including every site you are logged in to. No password is needed. The tool binds nothing itself; the port belongs to Brave.

To limit the risk:

- Keep the port on `localhost`. Never expose it to a network.
- When the tool starts Brave for a run, it quits Brave when the run finishes, so the port is closed again. Set `FB_PFP_KEEP_BRAVE_OPEN=1` only if you want the debug session to persist.
- Do not leave a debug-enabled Brave running all day if you can avoid it.
- Treat an unknown program connecting to port 9222 as a sign of compromise.
- Use a separate Brave profile for this tool if you want to keep other logins out of reach.
- Set `FB_PFP_EXPECTED_NAME` to your Facebook display name. The run then verifies the browser's logged-in account before changing anything, and refuses to act on a different account.

## What a run writes to disk

- `~/.fb_pfp/state.json`: image file names already used (only with `--cycle`). Written with private permissions (directory `0700`).
- `~/.fb_pfp/screenshots/`: screenshots of your Facebook page, written with mode `0600`. They are written only with `-v` or when a run fails. Delete them when you are done debugging; they are excluded from git and should not be kept around.
- `~/.fb_pfp/run.lock`: an empty lock file that serializes overlapping runs.

## Terms of service

Automating Facebook may break Meta's terms. You accept the risk of account restrictions. The tool does not try to get around logins, rate limits or consent screens.

## Disclaimer

Not affiliated with, endorsed by, or sponsored by Meta Platforms, Inc. Facebook is a trademark of Meta Platforms, Inc.
