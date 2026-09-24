"""Writes shared fragments into every page, so they're defined once.

    python tools/sync.py           # rewrite the marker regions from partials/
    python tools/sync.py --check   # exit 1 if any page has drifted

A page marks a region with a pair of comments:

    <!-- sync:header -->
    <!-- /sync:header -->

and the region is replaced with partials/header.html. The output is committed,
because the site has no build step at serve time. tools/check.py runs --check,
so a page edited by hand inside a region fails the check.

Every page must carry the header and footer regions.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTIALS = ROOT / "partials"
REQUIRED = ("header", "footer")
REGION = re.compile(r"(?P<open>[ \t]*<!-- sync:(?P<name>[a-z0-9-]+) -->\n)(?P<body>.*?)(?P<close>[ \t]*<!-- /sync:(?P=name) -->)", re.S)


def pages() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.html"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted(ROOT / p for p in out.splitlines()
                  if p and not p.startswith(("partials/", "tools/")))


def render(text: str) -> tuple[str, list[str]]:
    problems: list[str] = []
    found: set[str] = set()

    def fill(m: re.Match) -> str:
        name = m.group("name")
        found.add(name)
        partial = PARTIALS / f"{name}.html"
        if not partial.exists():
            problems.append(f"no partials/{name}.html")
            return m.group(0)
        body = partial.read_text(encoding="utf-8")
        if not body.endswith("\n"):
            body += "\n"
        return m.group("open") + body + m.group("close")

    out = REGION.sub(fill, text)
    for name in REQUIRED:
        if name not in found:
            problems.append(f"missing the sync:{name} region")
    return out, problems


def check() -> list[str]:
    """Errors for tools/check.py: drift and missing regions, one line each."""
    errors = []
    for page in pages():
        rel = page.relative_to(ROOT).as_posix()
        text = page.read_text(encoding="utf-8")
        out, problems = render(text)
        errors += [f"{rel}: {p}" for p in problems]
        if out != text:
            errors.append(f"{rel}: a shared region differs from partials/ (run python tools/sync.py)")
    return errors


def main() -> int:
    if "--check" in sys.argv:
        errors = check()
        for e in errors:
            print("ERROR:", e)
        return 1 if errors else 0
    changed = 0
    for page in pages():
        text = page.read_text(encoding="utf-8")
        out, problems = render(text)
        for p in problems:
            print(f"ERROR: {page.relative_to(ROOT).as_posix()}: {p}")
        if out != text:
            page.write_text(out, encoding="utf-8", newline="\n")
            changed += 1
            print("synced", page.relative_to(ROOT).as_posix())
    print(f"{changed} page(s) changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
