"""Fail if tracked text files contain em dashes or en dashes.

Usage: python scripts/check_text.py [FILE ...]
With no arguments, every file known to git is checked.
Exit status: 0 when clean, 1 when a match is found, 2 on a usage error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FORBIDDEN = {chr(0x2014): "em dash", chr(0x2013): "en dash"}
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".txt", ".svg", ".cfg", ".ini"}
TEXT_NAMES = {"LICENSE", "CODEOWNERS", ".gitignore", ".gitattributes", ".editorconfig"}


def tracked_files() -> list[Path]:
    """Return paths git knows about (tracked plus untracked, minus ignored)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(line) for line in out.splitlines() if line]


def is_text(path: Path) -> bool:
    """True for file types this check covers."""
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES


def scan(paths: list[Path]) -> list[str]:
    """Return one message per forbidden character found."""
    problems: list[str] = []
    for path in paths:
        if not path.is_file() or not is_text(path):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for char, name in FORBIDDEN.items():
                if char in line:
                    problems.append(f"{path}:{number}: {name}")
    return problems


def main(argv: list[str]) -> int:
    """Run the check; see the module docstring for exit codes."""
    paths = [Path(a) for a in argv] if argv else tracked_files()
    problems = scan(paths)
    for message in problems:
        print(message)
    if problems:
        print(f"{len(problems)} forbidden character(s) found. Use a comma, colon or hyphen instead.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
