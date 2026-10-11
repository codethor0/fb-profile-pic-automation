#!/bin/bash
# Scheduled-run wrapper: one command for cron or launchd.
#
#   PICS_DIR=~/Pictures/profile-pics ./run.sh
#
# PICS_DIR must point at a folder that holds only pictures you are happy to make
# public: whichever image is chosen becomes your profile picture. There is no
# default on purpose.
# FB_PFP_PYTHON optionally names the Python interpreter to use (for example the
# one inside a virtual environment). It defaults to python3.
set -euo pipefail

if [ -z "${PICS_DIR:-}" ]; then
  echo "run.sh: set PICS_DIR to a folder of profile pictures (no default, on purpose)." >&2
  exit 2
fi
if [ ! -d "$PICS_DIR" ]; then
  echo "run.sh: PICS_DIR is not a directory: $PICS_DIR" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${FB_PFP_PYTHON:-python3}"

exec "$PYTHON" "$SCRIPT_DIR/fb_change_pfp.py" --dir "$PICS_DIR" --cycle
