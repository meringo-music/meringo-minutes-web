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
  - every number in page copy has a source: a <span data-fact="id"> must
    hold exactly the value data/facts.json gives that id, and any other digit
    in visible copy fails unless it sits in a <time>, the app's own quoted
    words (data-lint="app"), the footer, or a pattern lint_rules.json allows;
  - /privacy/ keeps the shape the desk's page renderer relies on, and, when
    the desk repo sits beside this one, its render_page.build_page renders a
    dummy page into it (skipped when absent, as in CI);
  - /faq/'s FAQPage JSON-LD says exactly what the page shows: the same
    questions, in the same order, with the same answer text, and the same as
    assets/data/faq.json (JSON-LD is a data block, not a script, so the CSP
    allows it and it isn't counted as inline code);
  - shared and generated regions match their sources (tools/sync.py) and the
    colour tokens meet WCAG contrast in both themes (tools/contrast.py);
  - no tracked file holds a personal path or the checking model's name.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "tools" / "lint_rules.json").read_text(encoding="utf-8"))
FACTS = ROOT / "data" / "facts.json"
FACT_FIELDS = ("id", "value", "source", "method", "asOf")
TEMPLATE = "privacy/index.html"  # the page the desk's renderer borrows its shell from
FAQ_PAGE = "faq/index.html"  # generated from assets/data/faq.json by tools/sync.py
DIGIT_EXEMPT_TAGS = {"time", "footer"}

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
        # (tag, data-lint="app", exempt from the digit rule, data-fact id or None)
        self.stack: list[tuple[str, bool, bool, str | None]] = []
        self.blocks: list[tuple[str, str, bool]] = []  # (tag, text, is_app)
        self.buf: list[str] = []
        self.free: list[str] = []  # this block's text outside every digit exemption
        self.loose: list[tuple[str, str]] = []  # (tag, free text) for blocks whose free text has a digit
        self.fact_spans: list[tuple[str, str]] = []  # (fact id, text inside the element)
        self.fact_bufs: dict[int, list[str]] = {}  # stack index -> text so far
        self.buf_tag = "body"
        self.ids: set[str] = set()
        self.links: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.csp: list[str] = []
        self.canonical: list[str] = []
        self.inline_scripts = 0
        self.style_attrs = 0
        self.cta_state: str | None = None
        self.skip = 0  # inside <script>/<style>
        self.ld_blocks: list[str] = []  # the text of each <script type="application/ld+json">
        self._ld: list[str] | None = None

    # -- helpers
    def _app(self) -> bool:
        return any(app for _, app, _, _ in self.stack)

    def _exempt(self) -> bool:
        return any(exempt for _, _, exempt, _ in self.stack)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.blocks.append((self.buf_tag, text, self._app()))
        free = re.sub(r"\s+", " ", "".join(self.free)).strip()
        if re.search(r"\d", free):
            self.loose.append((self.buf_tag, free))
        self.buf = []
        self.free = []

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
            if (a.get("type") or "") == "application/ld+json":
                self._ld = []  # a data block: the CSP doesn't apply, nothing runs
            elif "src" not in a:
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
            app = a.get("data-lint") == "app"
            fact = a.get("data-fact")
            exempt = app or fact is not None or tag in DIGIT_EXEMPT_TAGS
            self.stack.append((tag, app, exempt, fact))
            if fact is not None:
                self.fact_bufs[len(self.stack) - 1] = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "script" and self._ld is not None:
            self.ld_blocks.append("".join(self._ld))
            self._ld = None
        if tag in BLOCKS:
            self._flush()
            self.buf_tag = "body"
        # pop to the matching tag (tolerates unclosed <p>/<li>)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for depth in range(len(self.stack) - 1, i - 1, -1):
                    if depth in self.fact_bufs:
                        text = re.sub(r"\s+", " ", "".join(self.fact_bufs.pop(depth))).strip()
                        self.fact_spans.append((self.stack[depth][3] or "", text))
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        if not self.skip:
            self.buf.append(data)
            for buf in self.fact_bufs.values():
                buf.append(data)
            # an exempt run still separates the free text on either side of it
            self.free.append(" " if self._exempt() else data)

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


def load_facts() -> tuple[dict[str, str], list[str]]:
    """({id: value}, errors). Every fact names its source, method and date."""
    errors: list[str] = []
    facts: dict[str, str] = {}
    for i, fact in enumerate(json.loads(FACTS.read_text(encoding="utf-8")).get("facts", [])):
        fid = str(fact.get("id") or f"entry {i + 1}")
        missing = [k for k in FACT_FIELDS if not str(fact.get(k, "")).strip()]
        if missing:
            errors.append(f"data/facts.json: {fid} has no {', '.join(missing)}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fact.get("asOf", ""))):
            errors.append(f"data/facts.json: {fid} asOf should be a YYYY-MM-DD date")
        if fid in facts:
            errors.append(f"data/facts.json: {fid} is listed twice")
        facts[fid] = str(fact.get("value", ""))
    return facts, errors


def template_errors(text: str) -> list[str]:
    """The shape the desk's page renderer (meringo-desk tools/render_page.py)
    needs from the page it borrows its shell from. It replaces the title, the
    meta description, the canonical link and the inside of <main class="page">
    by exact pattern, so each must appear once and in exactly this form."""
    errors = []
    once = [
        (r"<title>.*?</title>", "<title>…</title>"),
        (r'<meta name="description" content="[^"]*">', '<meta name="description" content="…">'),
        (r'<link rel="canonical" href="[^"]*">', '<link rel="canonical" href="…">'),
        (r'<main class="page">', '<main class="page"> (no other attributes on main)'),
        (r"<main\b", "<main>"),
    ]
    for pattern, what in once:
        n = len(re.findall(pattern, text, flags=re.S))
        if n != 1:
            errors.append(f"{TEMPLATE}: the desk template needs exactly one {what}, found {n}")
    if "application/ld+json" in text:
        errors.append(f"{TEMPLATE}: carries JSON-LD, which the desk renderer would copy onto a page it doesn't describe")
    header = re.search(r"<header\b.*?</header>", text, flags=re.S)
    if header and "aria-current" in header.group(0):
        errors.append(f"{TEMPLATE}: aria-current in the header would mark every rendered page as /privacy/ (site.js sets it at runtime)")
    if not re.search(r'<div id="content" tabindex="-1"></div>\s*<main class="page">', text):
        errors.append(f'{TEMPLATE}: the skip target <div id="content" tabindex="-1"></div> must sit just before <main class="page">')
    if text.count("</style>") > 1:
        errors.append(f"{TEMPLATE}: more than one </style>; the desk renderer adds table styles to exactly one")
    return errors


class FaqItems(HTMLParser):
    """What /faq/ shows: each <details class="faq-item">, its <summary> as the
    question and the rest of its text as the answer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []  # (id, question, answer)
        self._item: dict | None = None
        self._depth = 0  # <details> nesting inside the current item
        self._in_summary = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "details":
            if self._item is None and "faq-item" in (a.get("class") or "").split():
                self._item = {"id": a.get("id") or "", "q": [], "a": []}
                self._depth = 0
            elif self._item is not None:
                self._depth += 1
        if tag == "summary" and self._item is not None and self._depth == 0:
            self._in_summary = True

    def handle_endtag(self, tag):
        if tag == "summary":
            self._in_summary = False
        if tag == "details" and self._item is not None:
            if self._depth:
                self._depth -= 1
                return
            flat = lambda parts: re.sub(r"\s+", " ", "".join(parts)).strip()
            self.items.append((self._item["id"], flat(self._item["q"]), flat(self._item["a"])))
            self._item = None

    def handle_data(self, data):
        if self._item is not None:
            self._item["q" if self._in_summary else "a"].append(data)


def faq_parity(text: str) -> tuple[list[str], list[str]]:
    """(errors, notes). The FAQPage JSON-LD on /faq/ must say exactly what the
    page shows, question for question, and both must match faq.json."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "tools"))
    import sync  # noqa: E402

    errors: list[str] = []
    page = Page()
    page.feed(text)
    page.close()
    if len(page.ld_blocks) != 1:
        return [f"{FAQ_PAGE}: expected one FAQPage JSON-LD block, found {len(page.ld_blocks)}"], []
    try:
        ld = json.loads(page.ld_blocks[0])
    except json.JSONDecodeError as e:
        return [f"{FAQ_PAGE}: the JSON-LD doesn't parse: {e}"], []
    flat = lambda s: re.sub(r"\s+", " ", str(s)).strip()
    if ld.get("@type") != "FAQPage" or ld.get("@context") != "https://schema.org":
        errors.append(f"{FAQ_PAGE}: the JSON-LD is not a schema.org FAQPage")
    said = [(flat(q.get("name", "")), flat(q.get("acceptedAnswer", {}).get("text", "")))
            for q in ld.get("mainEntity", []) if q.get("@type") == "Question"]
    if len(said) != len(ld.get("mainEntity", [])):
        errors.append(f"{FAQ_PAGE}: an entry in the JSON-LD is not a Question")

    shown = FaqItems()
    shown.feed(text)
    shown.close()
    visible = [(q, a) for _, q, a in shown.items]
    source = [(flat(q["name"]), flat(q["acceptedAnswer"]["text"])) for q in sync.faq_jsonld()["mainEntity"]]

    for name, other in (("the visible page", visible), ("assets/data/faq.json", source)):
        if len(said) != len(other):
            errors.append(f"{FAQ_PAGE}: the JSON-LD has {len(said)} questions, {name} has {len(other)}")
            continue
        for i, (a, b) in enumerate(zip(said, other)):
            if a != b:
                k = 0 if a[0] != b[0] else 1
                errors.append(f"{FAQ_PAGE}: JSON-LD question {i + 1}'s {('question', 'answer')[k]} differs from {name}:\n"
                              f"      JSON-LD: {a[k][:120]}\n"
                              f"      {name}: {b[k][:120]}")
                break
    ids = [i for i, _, _ in shown.items]
    if len(set(ids)) != len(ids) or not all(ids):
        errors.append(f"{FAQ_PAGE}: every <details class=\"faq-item\"> needs its own id")
    notes = [] if errors else [f"{FAQ_PAGE}: JSON-LD matches the page and faq.json, {len(said)} questions"]
    return errors, notes


def desk_render(text: str) -> tuple[list[str], list[str]]:
    """(errors, notes). Renders a dummy page into /privacy/ with the desk's own
    render_page.build_page, imported read-only from the desk repo beside this
    one (or MERINGO_DESK). Skips, with a note, when the desk isn't there."""
    desk = Path(os.environ.get("MERINGO_DESK") or ROOT.parent / "meringo-desk")
    renderer = desk / "tools" / "render_page.py"
    if not renderer.is_file():
        return [], ["desk template: meringo-desk/tools/render_page.py is not beside this repo; render test skipped"]
    sys.dont_write_bytecode = True  # leave nothing behind in the desk repo
    spec = importlib.util.spec_from_file_location("desk_render_page", renderer)
    module = importlib.util.module_from_spec(spec)
    meta = {"title": "Template test — Meringo Minutes",
            "description": "A dummy page, rendered into the privacy page's shell by the desk's renderer."}
    canonical = RULES["base"] + "/template-test/"
    body = "# Template test\n\nA paragraph the renderer converts.\n\n## A section\n\n- one item\n- another item"
    try:
        spec.loader.exec_module(module)
        inner, _ = module.md_to_html(body)
        out = module.build_page(text, meta, inner, canonical)
    except Exception as e:  # a Refusal, or the renderer's API changed under us
        return [f"desk template: render_page could not render into {TEMPLATE}: {type(e).__name__}: {e}"], []

    errors = []
    page = Page()
    page.feed(out)
    page.close()
    if page.csp != [RULES["csp"]]:
        errors.append("desk template: the rendered page lost its CSP")
    if page.canonical != [canonical]:
        errors.append(f"desk template: the rendered page's canonical is {page.canonical}, not {canonical}")
    if "<title>Template test — Meringo Minutes</title>" not in out:
        errors.append("desk template: the rendered page's <title> was not replaced")
    if [t for t, _, _ in page.blocks if t == "h1"] != ["h1"] or "Template test" not in out.split("<main", 1)[1]:
        errors.append("desk template: the rendered page doesn't carry the dummy body as its one <h1>")
    if "privacy" in out.split("<main", 1)[1].split("</main>", 1)[0].lower():
        errors.append("desk template: text from /privacy/'s own <main> survived the render")
    for region in ("header", "footer"):
        rx = re.compile(rf"<!-- sync:{region} -->.*?<!-- /sync:{region} -->", re.S)
        if rx.search(out) is None or rx.search(out).group(0) != rx.search(text).group(0):
            errors.append(f"desk template: the shared {region} changed in the render")
    return errors, ["desk template: render_page.build_page rendered a dummy page into /privacy/ cleanly"] if not errors else []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errors: list[str] = []
    notes: list[str] = []
    files = tracked_files()
    pages = sorted(p for p in files if p.suffix == ".html" and not {"tools", "partials"} & set(p.relative_to(ROOT).parts))
    parsed: dict[Path, Page] = {}

    for path in pages:
        page = Page()
        page.feed(path.read_text(encoding="utf-8"))
        page.close()
        parsed[path] = page

    banned = [(re.compile(r["pattern"], re.I), r["why"]) for r in RULES["banned"]]
    voice = [(re.compile(r["pattern"], re.I), r["why"]) for r in RULES["voice"]]
    allowed = [a["phrase"] if isinstance(a, dict) else a for a in RULES["allowed_phrases"]]
    digits_allowed = [re.compile(a["pattern"]) for a in RULES["digits"]["allowed"]]
    facts, fact_errors = load_facts()
    errors += fact_errors
    used_facts: set[str] = set()
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

        # Numbers: each one sourced in data/facts.json
        for fid, text in page.fact_spans:
            used_facts.add(fid)
            if fid not in facts:
                errors.append(f"{rel}: data-fact=\"{fid}\" is not in data/facts.json")
            elif text != facts[fid]:
                errors.append(f"{rel}: data-fact=\"{fid}\" reads \"{text}\", but data/facts.json says \"{facts[fid]}\"")
        for tag, free in page.loose:
            rest = free
            for rx in digits_allowed:
                rest = rx.sub(" ", rest)
            m = re.search(r"\S*\d\S*", rest)
            if m:
                errors.append(f"{rel}: <{tag}> \"{m.group(0)}\" is a number with no source — "
                              f"{RULES['digits']['why']}\n      in: {free[:140]}")

        if rel == TEMPLATE:
            text = path.read_text(encoding="utf-8")
            errors += template_errors(text)
            desk_errors, desk_notes = desk_render(text)
            errors += desk_errors
            notes += desk_notes

        if page.ld_blocks and rel != FAQ_PAGE:
            errors.append(f"{rel}: carries JSON-LD; only {FAQ_PAGE} has any yet, and check.py checks only that one")
        if rel == FAQ_PAGE:
            faq_errors, faq_notes = faq_parity(path.read_text(encoding="utf-8"))
            errors += faq_errors
            notes += faq_notes

    if FAQ_PAGE not in {p.relative_to(ROOT).as_posix() for p in pages}:
        errors.append(f"{FAQ_PAGE} is missing")

    if len(set(states.values())) > 1:
        errors.append(f"pages disagree on data-cta-state: {states}")
    if TEMPLATE not in {p.relative_to(ROOT).as_posix() for p in pages}:
        errors.append(f"{TEMPLATE} is missing; the desk's page renderer uses it as its template")
    for fid in sorted(set(facts) - used_facts):
        notes.append(f"data/facts.json: {fid} is not used on any page")

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

    # Shared regions and colour contrast (their own scripts, run here too)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "tools"))
    import contrast  # noqa: E402
    import sync  # noqa: E402
    errors += sync.check()
    errors += contrast.check()

    for n in sorted(set(notes)):
        print("note:", n)
    for e in errors:
        print("ERROR:", e)
    print(f"\n{len(pages)} page(s), {len(files)} tracked file(s): "
          + ("clean." if not errors else f"{len(errors)} error(s)."))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
