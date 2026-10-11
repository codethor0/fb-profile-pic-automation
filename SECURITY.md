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
- Do not leave a debug-enabled Brave running all day if you can avoid it. Let the tool start Brave for the run, then quit Brave.
- Treat an unknown program connecting to port 9222 as a sign of compromise.
- Use a separate Brave profile for this tool if you want to keep other logins out of reach.

## What a run writes to disk

- `~/.fb_pfp/state.json`: image file names already used (only with `--cycle`).
- `~/.fb_pfp/screenshots/`: screenshots of your Facebook page. They are written only with `-v` or when a run fails. Delete them when you are done. They are excluded from git.

## Terms of service

Automating Facebook may break Meta's terms. You accept the risk of account restrictions. The tool does not try to get around logins, rate limits or consent screens.

## Disclaimer

Not affiliated with, endorsed by, or sponsored by Meta Platforms, Inc. Facebook is a trademark of Meta Platforms, Inc.
