# Contributing

Thanks for helping. This is a small tool, so changes should stay small and easy to review.

## Set up

```bash
git clone https://github.com/codethor0/fb-profile-pic-automation.git
cd fb-profile-pic-automation
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Check your work

```bash
.venv/bin/python -m pytest
.venv/bin/bandit -q -r src -ll
python3 scripts/check_text.py
```

All three must pass. The same checks run in CI on every pull request. The tests are offline: they need no browser and no network, and they must pass on Linux even though the tool targets macOS. Anything specific to one machine is passed in by the test, not assumed.

## Pull requests

`main` is protected, so every change goes through a pull request and must pass CI.

1. Fork the repository and make a branch.
2. Make one focused change. A bug fix includes a test that fails without the fix.
3. Update the README or docs in the same pull request if behavior changes.
4. Open the pull request and fill in the template.

Explain why in the commit message, not only what.

## Project rules

- No credentials. The tool must never ask for, store, log or send a password, cookie or token.
- The debug port stays on `localhost`. Do not add documentation that suggests otherwise.
- No shell strings. Use fixed argument lists with `subprocess`. No `shell=True`, `eval` or `exec`.
- Check input before using it, and fail with a clear message.
- No bare `except:`. A caught exception is logged or raised again.
- Every wait has a timeout.
- Look up buttons by visible text, and keep lookups inside the profile picture dialog.
- Write state with a temporary file and a rename.
- Keep runtime dependencies to a minimum. A new dependency needs a reason in the pull request.
- No photos, screenshots, account names or credentials in the repository, including test data. Tests create their own files.
- Docs must match the code. If they disagree, fix whichever is wrong.

## Writing style

- Plain, direct sentences. Say what the tool does, how, and where it stops working.
- No em dashes or en dashes. Use a comma, colon or hyphen. CI enforces this.
- No marketing words and no filler.
- Use code blocks for commands, and make sure they run as written.

## Security issues

Do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Conduct

Be kind and stay on topic. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
