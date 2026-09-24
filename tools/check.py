"""Checks meringominutes.app before every pull request.

    python tools/check.py

Exits 0 when clean, 1 on any error. Standard library only.

What it checks, and why:
  - every page carries the same Content-Security-Policy, so the privacy claim
    ("no third-party requests") is enforced by the browser, not just promised;
  - nothing is loaded from another origin, and no inline script or style
    exists (the CSP would block it silently);
  - every internal link and fragment resolves;
  - the copy rules in tools/lint_rules.json (banned phrases, first-person
    voice, "by default" on locality claims, the full product name in titles);
  - every page is in the same launch state;
  - no tracked file holds a personal path or the checking model's name.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "tools" / "lint_rules.json").read_text(encoding="utf-8"))

BLOCKS = {"p", "li", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd",
          "td", "th", "blockquote", "summary", "title", "caption", "label", "button"}
HEADINGS = {"title", "h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
LOADS = {  # tag -> attributes that make the browser fetch something
    "link": ("href",), "script": ("src",), "img": ("src", "srcset"),
    "source": ("src", "srcset"), "audio": ("src",), "video": ("src", "poster"),
    "iframe": ("src",), "embed": ("src",), "object": ("data",),
}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []   # (tag, inside data-lint="app")
        self.blocks: list[tuple[str, str, bool]] = []  # (tag, text, is_app)
        self.buf: list[str] = []
        self.buf_tag = "body"
        self.ids: set[str] = set()
        self.links: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.csp: list[str] = []
        self.canonical: list[str] = []
        self.inline_scripts = 0
        self.style_attrs = 0
        self.cta_state: str | None = None
        self.skip = 0  # inside <script>/<style>

    # -- helpers
    def _app(self) -> bool:
        return any(app for _, app in self.stack)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.blocks.append((self.buf_tag, text, self._app()))
        self.buf = []

    # -- parser hooks
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if "style" in a:
            self.style_attrs += 1
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp.append(a.get("content") or "")
        if tag == "body":
            self.cta_state = a.get("data-cta-state")
        if tag == "script":
            if "src" not in a and (a.get("type") or "") != "application/ld+json":
                self.inline_scripts += 1
            self.skip += 1
        if tag == "style":
            self.inline_scripts += 1  # an inline <style> block is blocked by the CSP too
            self.skip += 1
        rel = (a.get("rel") or "").lower().split()
        if tag == "link" and ("canonical" in rel or "alternate" in rel):
            self.canonical.append(a.get("href") or "")
        else:
            for attr in LOADS.get(tag, ()):
                if a.get(attr):
                    self.links.append((tag, attr, a[attr]))
        if tag == "a" and a.get("href"):
            self.links.append(("a", "href", a["href"]))
        if tag in BLOCKS:
            self._flush()
            self.buf_tag = tag
        if tag not in VOID:
            self.stack.append((tag, a.get("data-lint") == "app"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in BLOCKS:
            self._flush()
            self.buf_tag = "body"
        # pop to the matching tag (tolerates unclosed <p>/<li>)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line.strip()]


def resolve(url_path: str, page: Path) -> Path:
    if url_path.startswith("/"):
        target = ROOT / unquote(url_path.lstrip("/"))
    else:
        target = (page.parent / unquote(url_path)).resolve()
    if url_path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errors: list[str] = []
    notes: list[str] = []
    files = tracked_files()
    pages = sorted(p for p in files if p.suffix == ".html" and "tools" not in p.parts)
    parsed: dict[Path, Page] = {}

    for path in pages:
        page = Page()
        page.feed(path.read_text(encoding="utf-8"))
        page.close()
        parsed[path] = page

    banned = [(re.compile(r["pattern"], re.I), r["why"]) for r in RULES["banned"]]
    voice = [(re.compile(r["pattern"], re.I), r["why"]) for r in RULES["voice"]]
    allowed = RULES["allowed_phrases"]
    locality = re.compile(RULES["locality"]["pattern"], re.I)
    requires = RULES["locality"]["requires"].lower()
    states = {}

    for path, page in parsed.items():
        rel = path.relative_to(ROOT).as_posix()

        # CSP, inline code
        if page.csp != [RULES["csp"]]:
            errors.append(f"{rel}: CSP meta missing or different from lint_rules.json")
        if page.inline_scripts:
            errors.append(f"{rel}: {page.inline_scripts} inline <script>/<style> block(s); the CSP blocks them")
        if page.style_attrs:
            errors.append(f"{rel}: {page.style_attrs} style=\"\" attribute(s); the CSP blocks them")
        states[rel] = page.cta_state
        if rel != "404.html":
            want = RULES["base"] + "/" + (rel[:-len("index.html")] if rel.endswith("index.html") else rel)
            if page.canonical != [want]:
                errors.append(f"{rel}: canonical should be exactly {want}, found {page.canonical}")

        # Links and loads
        for tag, attr, value in page.links:
            for ref in ([v.strip().split(" ")[0] for v in value.split(",")] if attr == "srcset" else [value]):
                parts = urlsplit(ref)
                if parts.scheme in ("http", "https") or ref.startswith("//"):
                    if tag != "a":
                        errors.append(f"{rel}: <{tag} {attr}> loads from another origin: {ref}")
                    continue
                if parts.scheme in ("mailto", "tel", "data"):
                    continue
                if parts.scheme:
                    errors.append(f"{rel}: unexpected URL scheme: {ref}")
                    continue
                if not parts.path:  # same-page fragment
                    if parts.fragment and parts.fragment not in page.ids:
                        errors.append(f"{rel}: #{parts.fragment} has no matching id")
                    continue
                target = resolve(parts.path, path)
                if not target.exists():
                    errors.append(f"{rel}: {ref} does not resolve ({target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else target})")
                elif parts.fragment and target.suffix == ".html":
                    other = parsed.get(target)
                    if other and parts.fragment not in other.ids:
                        errors.append(f"{rel}: {ref} — no id '{parts.fragment}' in {target.relative_to(ROOT).as_posix()}")

        # Copy rules
        h1s = sum(1 for tag, _, _ in page.blocks if tag == "h1")
        if h1s != 1:
            errors.append(f"{rel}: expected one <h1>, found {h1s}")
        for tag, text, is_app in page.blocks:
            checked = text
            for phrase in allowed:
                if phrase.lower() in checked.lower():
                    notes.append(f"{rel}: allowed phrase used: \"{phrase}\"")
                    checked = re.sub(re.escape(phrase), " ", checked, flags=re.I)
            for rx, why in banned:
                m = rx.search(checked)
                if m:
                    errors.append(f"{rel}: <{tag}> \"{m.group(0)}\" — {why}\n      in: {text[:140]}")
            if not is_app:
                for rx, why in voice:
                    m = rx.search(checked)
                    if m:
                        errors.append(f"{rel}: <{tag}> \"{m.group(0)}\" — {why}\n      in: {text[:140]}")
                if locality.search(checked) and requires not in checked.lower():
                    errors.append(f"{rel}: <{tag}> locality claim without \"{RULES['locality']['requires']}\" — {RULES['locality']['why']}\n      in: {text[:140]}")
            if tag in HEADINGS and re.search(r"(?<!Meringo )\bMinutes\b", text):
                errors.append(f"{rel}: <{tag}> uses \"Minutes\" without \"Meringo\": {text[:100]}")

    if len(set(states.values())) > 1:
        errors.append(f"pages disagree on data-cta-state: {states}")

    # Every tracked file: personal paths, the checking model's name
    personal = [re.compile(r"[A-Za-z]:" + r"\\\\?" + "Users", re.I), re.compile("/" + "Users" + "/"),
                re.compile(r"\bC:" + r"[\\/]" + "Source", re.I)]
    forbidden = set(RULES["forbidden_token_sha256"])
    for path in files:
        if path.suffix.lower() in {".woff2", ".png", ".webp", ".ico", ".m4a", ".jpg", ".pdf"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for rx in personal:
            if rx.search(text):
                errors.append(f"{rel}: contains a local machine path ({rx.pattern})")
        for token in set(re.findall(r"[a-z0-9]+", text.lower())):
            if hashlib.sha256(token.encode()).hexdigest() in forbidden:
                errors.append(f"{rel}: contains a forbidden token (the checking model's name)")

    for n in sorted(set(notes)):
        print("note:", n)
    for e in errors:
        print("ERROR:", e)
    print(f"\n{len(pages)} page(s), {len(files)} tracked file(s): "
          + ("clean." if not errors else f"{len(errors)} error(s)."))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
