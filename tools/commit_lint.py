"""Fails if any commit message in a range carries AI attribution.

    python tools/commit_lint.py BASE HEAD     # checks BASE..HEAD
    python tools/commit_lint.py "" HEAD       # checks HEAD alone

The owner's rule: no commit in this repo says or implies how it was written.
No co-author trailers, no session trailers, no generator links. The checks
workflow runs this on every pull request and on every push to main.
"""

from __future__ import annotations

import re
import subprocess
import sys

BANNED = re.compile(r"co-authored-by|claude-session|claude\.ai/code|generated with", re.I)
ZERO = re.compile(r"^0+$")


def messages(base: str, head: str) -> list[tuple[str, str]]:
    rng = head if not base or ZERO.match(base) else f"{base}..{head}"
    args = ["git", "log", "--format=%H%x00%B%x1e", rng]
    if rng == head:
        args.insert(2, "-1")
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return [tuple(c.strip("\n").split("\x00", 1)) for c in out.split("\x1e") if c.strip()]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else ""
    head = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    bad = 0
    commits = messages(base, head)
    for sha, body in commits:
        for line in body.splitlines():
            if BANNED.search(line):
                print(f"ERROR: {sha[:10]} carries AI attribution: {line.strip()}")
                bad += 1
    print(f"{len(commits)} commit(s) checked: " + ("clean." if not bad else f"{bad} problem line(s)."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
