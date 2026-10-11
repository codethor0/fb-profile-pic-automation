#!/bin/bash
# Scheduled-run wrapper: one command for cron/launchd.
# Put your candidate profile pictures in PICS_DIR, then schedule this script.
set -euo pipefail

PICS_DIR="${PICS_DIR:-$HOME/Downloads}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/fb_change_pfp.py" --dir "$PICS_DIR" --cycle
