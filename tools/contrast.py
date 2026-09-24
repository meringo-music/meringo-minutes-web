"""WCAG contrast for the site's colour tokens, in both themes.

    python tools/contrast.py

Reads the token blocks in assets/css/site.css:
  - dark: the first :root { … } block;
  - light: :root[data-theme="light"] { … }, and the copy inside
    @media (prefers-color-scheme: light), which must be identical.

tools/check.py calls check(). Text pairs need 4.5:1 (WCAG 2.2 AA, 1.4.3);
the focus ring needs 3:1 against the page (1.4.11).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "assets" / "css" / "site.css"

TEXT = 4.5
UI = 3.0
PAIRS = [  # (foreground, background, minimum)
    *[(fg, bg, TEXT) for fg in ("text", "text-2") for bg in ("bg", "surface-1", "surface-2")],
    ("text-3", "bg", TEXT), ("text-3", "surface-1", TEXT),
    ("heading", "bg", TEXT),
    ("accent-ink", "bg", TEXT), ("accent-ink", "surface-1", TEXT),
    ("on-accent", "accent", TEXT),
    *[(fg, "app-window", TEXT) for fg in ("app-text", "app-text-2", "app-traced-ink", "app-setaside-ink")],
    ("focus", "bg", UI), ("focus", "surface-1", UI),
]


def block(css: str, selector_rx: str) -> str:
    m = re.search(selector_rx + r"\s*\{", css)
    if not m:
        raise SystemExit(f"contrast: no block matching {selector_rx}")
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[m.end():i - 1]


def tokens(body: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip().upper()
            for m in re.finditer(r"--([a-z0-9-]+)\s*:\s*([^;]+);", body)}


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def themes(css: str) -> tuple[dict, dict, dict]:
    dark = tokens(block(css, r"(?m)^:root"))
    light = tokens(block(css, r':root\[data-theme="light"\]'))
    media = tokens(block(block(css, r"@media \(prefers-color-scheme: light\)"),
                         r':root:not\(\[data-theme="dark"\]\)'))
    return dark, light, media


def check(verbose: bool = False) -> list[str]:
    css = CSS.read_text(encoding="utf-8")
    dark, light_explicit, light_media = themes(css)
    errors = []
    if light_explicit != light_media:
        diff = sorted(set(light_explicit.items()) ^ set(light_media.items()))
        errors.append(f"site.css: the two light-theme blocks differ: {diff}")
    light = {**dark, **light_explicit}  # light overrides; anything unset falls back
    for name, theme in (("dark", dark), ("light", light)):
        for fg, bg, minimum in PAIRS:
            a, b = theme.get(fg), theme.get(bg)
            if not (a and b and a.startswith("#") and b.startswith("#")):
                errors.append(f"contrast ({name}): --{fg} or --{bg} is not a hex colour")
                continue
            r = ratio(a, b)
            if verbose:
                print(f"{name:5} {fg:>17} on {bg:<10} {a} / {b}  {r:5.2f}:1 {'ok' if r >= minimum else 'FAIL'}")
            if r < minimum:
                errors.append(f"contrast ({name}): --{fg} {a} on --{bg} {b} is {r:.2f}:1, needs {minimum}:1")
    return errors


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errs = check(verbose=True)
    for e in errs:
        print("ERROR:", e)
    sys.exit(1 if errs else 0)
