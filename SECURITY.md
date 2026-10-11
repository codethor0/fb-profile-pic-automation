# Security Policy

## Design guarantees

- **No credentials are handled, stored, or transmitted.** The tool drives
  *your own* logged-in browser over the local Chrome DevTools Protocol
  (localhost only). There is nothing to leak: no passwords, no cookies,
  no tokens, no network endpoint beyond Facebook itself.
- The debug port binds to `localhost` only. Do not expose port 9222 to a
  network interface — any local process could then control the browser.

## Reporting a vulnerability

Please open a private security advisory on GitHub, or email the maintainer
via the address on their GitHub profile. Do not file public issues for
security-relevant bugs.

## Scope notes

- Automating interaction with Facebook may violate Meta's Terms of Service.
  This project is provided for educational and personal-use purposes on
  accounts you own; you accept the risk of account restrictions.
- This tool never bypasses authentication, rate limits, or consent screens.
