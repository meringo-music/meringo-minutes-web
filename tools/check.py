"""Checks meringominutes.app before every pull request.

    python tools/check.py
    python tools/check.py --capture <capture folder>   # also re-extract the demo and diff it

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
  - the home page's SoftwareApplication JSON-LD names the product in full,
    repeats og:description, and carries no offers before launch and no rating;
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
import html
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
# Words someone else wrote, quoted: the app's own (data-lint="app") and the demo
# script (data-lint="reference"). Exempt from the voice rules, never the bans.
QUOTED = {"app", "reference"}

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
        # (tag, text, is_app, own): own is the text outside any data-lint="app"
        # quotation, so an inline quote of the app is exempt from the voice
        # and locality rules just as a quoted block is
        self.blocks: list[tuple[str, str, bool, str]] = []
        self.buf: list[str] = []
        self.own: list[str] = []
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
            own = re.sub(r"\s+", " ", "".join(self.own)).strip()
            self.blocks.append((self.buf_tag, text, self._app(), own))
        free = re.sub(r"\s+", " ", "".join(self.free)).strip()
        if re.search(r"\d", free):
            self.loose.append((self.buf_tag, free))
        self.buf = []
        self.own = []
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
            app = a.get("data-lint") in QUOTED
            fact = a.get("data-fact")
            exempt = app or fact is not None or tag in DIGIT_EXEMPT_TAGS or "data-demo" in a
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
            self.own.append(" " if self._app() else data)
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


def software_ld(text: str, cta_state: str | None) -> tuple[list[str], list[str]]:
    """(errors, notes). The home page's SoftwareApplication JSON-LD: one block,
    the full product name, the same descriptor as og:description, and, before
    launch, no offers (nothing is for sale) and never a rating (there are none)."""
    page = Page()
    page.feed(text)
    page.close()
    if len(page.ld_blocks) != 1:
        return [f"{HOME}: expected one SoftwareApplication JSON-LD block, found {len(page.ld_blocks)}"], []
    raw = page.ld_blocks[0]
    try:
        ld = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"{HOME}: the JSON-LD doesn't parse: {e}"], []
    errors = []
    if ld.get("@context") != "https://schema.org" or ld.get("@type") != "SoftwareApplication":
        errors.append(f"{HOME}: the JSON-LD is not a schema.org SoftwareApplication")
    if ld.get("name") != "Meringo Minutes":
        errors.append(f"{HOME}: the JSON-LD name should be exactly \"Meringo Minutes\"")
    og = re.search(r'<meta property="og:description" content="([^"]*)">', text)
    if not og or ld.get("description") != html.unescape(og.group(1)):
        errors.append(f"{HOME}: the JSON-LD description should be the page's og:description, word for word")
    flat = json.dumps(ld)
    for key in ("aggregateRating", "review"):
        if f'"{key}"' in flat:
            errors.append(f"{HOME}: the JSON-LD carries {key}; there are no ratings or reviews to cite")
    if cta_state == "prelaunch" and '"offers"' in flat:
        errors.append(f"{HOME}: the JSON-LD carries offers, but the site is in the prelaunch state")
    if "</" in raw:
        errors.append(f"{HOME}: the JSON-LD holds a raw '</'; escape it as '<\\/'")
    return errors, ([f"{HOME}: SoftwareApplication JSON-LD checked (no offers while {cta_state})"] if not errors else [])


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
    if [t for t, *_ in page.blocks if t == "h1"] != ["h1"] or "Template test" not in out.split("<main", 1)[1]:
        errors.append("desk template: the rendered page doesn't carry the dummy body as its one <h1>")
    if "privacy" in out.split("<main", 1)[1].split("</main>", 1)[0].lower():
        errors.append("desk template: text from /privacy/'s own <main> survived the render")
    for region in ("header", "footer"):
        rx = re.compile(rf"<!-- sync:{region} -->.*?<!-- /sync:{region} -->", re.S)
        if rx.search(out) is None or rx.search(out).group(0) != rx.search(text).group(0):
            errors.append(f"desk template: the shared {region} changed in the render")
    return errors, ["desk template: render_page.build_page rendered a dummy page into /privacy/ cleanly"] if not errors else []


HOME = "index.html"
DEMO_JSON = ROOT / "assets" / "data" / "demo.json"
ANNOTATIONS = ROOT / "tools" / "demo" / "annotations.json"
# Where each scoreboard count is also stated as a fact elsewhere on the site.
TALLY_FACTS = {"lineNo": "demo-anchor-miss", "anchored": "demo-anchored", "linePartly": "demo-anchor-partial",
               "traps": "ask-unanswerable", "trapsRefused": "ask-unanswerable-refused"}
BUDGET = {"html": 90_000, "css": 30_000, "js": 20_000, "img": 200_000}  # the plan's home page budget, bytes
IMPORT = re.compile(r"""^\s*(?:import|export)\b(?!\s*\()[^'"]*?(?:from\s*)?['"]([^'"]+\.js)['"]""", re.M)  # not import()


def region_text(page: str, name: str) -> str | None:
    m = re.search(rf"<!-- sync:{name} -->(.*?)<!-- /sync:{name} -->", page, re.S)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", html.unescape(text))


def demo_errors(facts: dict[str, str], forbidden: set[str]) -> tuple[list[str], list[str]]:
    """(errors, notes) for the home page's demo, from the committed files alone
    (no capture needed, so CI runs it):
      - every app string in demo.json is in the page's no-JavaScript region;
      - every annotation's SHA-256 is an app string's, and every app string has one;
      - the recording is the capture's, by SHA-256;
      - no app string holds the checking model's name;
      - the scoreboard agrees with the facts the rest of the site states;
      - my notes and captions, which demo.js puts on the page, follow the copy rules."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "tools" / "demo"))
    import build_demo as bd  # noqa: E402

    errors: list[str] = []
    demo = json.loads(DEMO_JSON.read_text(encoding="utf-8"))
    app = demo["app"]
    page = (ROOT / HOME).read_text(encoding="utf-8")
    shown = region_text(page, "demo")
    if shown is None:
        return [f"{HOME}: no sync:demo region (the demo without JavaScript)"], []

    flat = lambda s: re.sub(r"\s+", " ", s).strip()
    strings = [text for _, _, text in bd.app_items(app) if "\n" not in text]
    for ask in app["asks"]:
        strings.append(ask["q"])
        for s in ask["answer"]:
            strings.append(s["text"])
            strings += [f'{c["t"]} {c["speaker"]}: {c["text"]}' for c in s["cites"]]
        strings += [ask["footnote"]] if ask["footnote"] else []
    strings += [app["chrome"]["setAsideHeading"], app["chrome"]["setAsideLine"], app["summary"]["heading"]]
    for s in strings:
        if flat(s) not in shown:
            errors.append(f"{HOME}: the no-JavaScript demo is missing an app string from demo.json: {s[:80]}")

    everything = [text for _, _, text in bd.app_items(app)] + list(app["chrome"].values())
    everything += [l["text"] for l in app["transcript"]]
    for s in everything:
        if any(hashlib.sha256(t.encode()).hexdigest() in forbidden for t in re.findall(r"[a-z0-9]+", s.lower())):
            errors.append("demo.json: an app string names the checking model")

    keys = {bd.key_of(text): where for _, where, text in bd.app_items(app)}
    notes = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    filed = set()
    for kind in ("summary", "asks"):
        for a in notes[kind]:
            if a["sha256"] not in keys:
                errors.append(f"annotations.json: {kind} {a.get('row') or a.get('n')} ({a.get('excerpt', '')[:40]}) "
                              "matches no app string in demo.json; re-audit it")
            filed.add(a["sha256"])
    for k, where in keys.items():
        if k not in filed:
            errors.append(f"annotations.json: no annotation for {where}")
        if k[:16] not in demo["site"]["audit"]:
            errors.append(f"demo.json: site.audit has nothing for {where}")

    audio = ROOT / demo["provenance"]["audio"]["url"].lstrip("/")
    if not audio.is_file() or hashlib.sha256(audio.read_bytes()).hexdigest() != bd.AUDIO_SHA256:
        errors.append(f"{audio.relative_to(ROOT).as_posix()}: missing, or not the capture's recording (SHA-256)")

    counts = bd.tally(demo)
    for key, fid in TALLY_FACTS.items():
        if facts.get(fid) != str(counts[key]):
            errors.append(f"the demo's scoreboard counts {key} = {counts[key]}, but data/facts.json has {fid} = {facts.get(fid)}")

    rules = [(re.compile(r["pattern"], re.I), r["why"]) for r in RULES["banned"] + RULES["voice"]]
    site = demo["site"]
    copy = [a["note"] for a in site["audit"].values() if a.get("note")]
    copy += [v for v in site["captions"].values() if isinstance(v, str)] + site["captions"]["score"]
    copy += [a["label"] for a in site["audit"].values() if a.get("label")]
    for text in copy:
        for rx, why in rules:
            m = rx.search(text)
            if m:
                errors.append(f"demo.json site copy: \"{m.group(0)}\" — {why}\n      in: {text[:140]}")
    return errors, ([f"demo: {len(keys)} app strings annotated, scoreboard {counts}"] if not errors else [])


def module_graph(entry: Path) -> set[Path]:
    """The JavaScript a page loads through static imports and re-exports, from
    one module. Dynamic import() is left out: it loads only when it runs."""
    seen: set[Path] = set()
    todo = [entry]
    while todo:
        f = todo.pop()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        for spec in IMPORT.findall(f.read_text(encoding="utf-8")):
            todo.append(ROOT / spec.lstrip("/") if spec.startswith("/") else (f.parent / spec).resolve())
    return seen


def budget_errors() -> tuple[list[str], list[str]]:
    """The home page against the plan's budget, in bytes as served; the audio
    isn't counted, nor vendored code. A <picture> counts its largest WebP,
    since a visitor downloads one of its files and every current browser
    takes the WebP over the PNG fallback."""
    text = (ROOT / HOME).read_text(encoding="utf-8")
    size = lambda f: len(f.read_bytes().replace(b"\r\n", b"\n"))  # as served: the repo stores LF
    js: set[Path] = set()
    for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', text):
        js |= module_graph(ROOT / src.lstrip("/"))
    js = {f for f in js if "vendor" not in f.parts}
    css = sum(size(ROOT / h.lstrip("/")) for h in re.findall(r'<link rel="stylesheet" href="([^"]+)"', text))
    img = 0
    for pic in re.findall(r"<picture>(.*?)</picture>", text, re.S):
        files = re.findall(r'(?:src|srcset)="([^" ]+)', pic)
        webp = [u for u in files if u.endswith(".webp")]  # what every current browser picks
        img += max((ROOT / u.lstrip("/")).stat().st_size for u in (webp or files))
    outside = re.sub(r"<picture>.*?</picture>", "", text, flags=re.S)
    img += sum((ROOT / u.lstrip("/")).stat().st_size for u in re.findall(r'<img[^>]*\bsrc="(/[^"]+)"', outside))
    sizes = {"html": len(text.encode("utf-8")), "css": css, "js": sum(size(f) for f in js), "img": img}
    errors = [f"{HOME}: {k.upper()} is {v:,} bytes, over the budget of {BUDGET[k]:,}" for k, v in sizes.items() if v > BUDGET[k]]
    return errors, [f"{HOME} budget: " + ", ".join(f"{k} {v:,} of {BUDGET[k]:,}" for k, v in sizes.items())]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    capture = None
    if "--capture" in sys.argv:
        i = sys.argv.index("--capture")
        if i + 1 >= len(sys.argv):
            print("usage: python tools/check.py [--capture <capture folder>]")
            return 2
        capture = sys.argv[i + 1]
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
        h1s = sum(1 for tag, *_ in page.blocks if tag == "h1")
        if h1s != 1:
            errors.append(f"{rel}: expected one <h1>, found {h1s}")
        for tag, text, is_app, own in page.blocks:
            checked = text
            for phrase in allowed:
                if phrase.lower() in checked.lower():
                    notes.append(f"{rel}: allowed phrase used: \"{phrase}\"")
                    checked = re.sub(re.escape(phrase), " ", checked, flags=re.I)
                    own = re.sub(re.escape(phrase), " ", own, flags=re.I)
            for rx, why in banned:
                m = rx.search(checked)
                if m:
                    errors.append(f"{rel}: <{tag}> \"{m.group(0)}\" — {why}\n      in: {text[:140]}")
            if not is_app:
                for rx, why in voice:
                    m = rx.search(own)
                    if m:
                        errors.append(f"{rel}: <{tag}> \"{m.group(0)}\" — {why}\n      in: {text[:140]}")
                if locality.search(own) and requires not in own.lower():
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

        if page.ld_blocks and rel not in (FAQ_PAGE, HOME):
            errors.append(f"{rel}: carries JSON-LD; only {FAQ_PAGE} and {HOME} have any, and check.py checks only those")
        if rel == HOME:
            ld_errors, ld_notes = software_ld(path.read_text(encoding="utf-8"), page.cta_state)
            errors += ld_errors
            notes += ld_notes
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

    # The demo, and the home page's budget
    more, more_notes = demo_errors(facts, forbidden)
    errors += more
    notes += more_notes
    more, more_notes = budget_errors()
    errors += more
    notes += more_notes
    if capture:
        import build_demo  # noqa: E402  (imported by demo_errors)
        print(f"re-extracting the demo from {Path(capture).name}:")
        if build_demo.main(["--capture", capture, "--check"]) != 0:
            errors.append("the demo differs from a fresh extraction of the capture (see above)")

    for n in sorted(set(notes)):
        print("note:", n)
    for e in errors:
        print("ERROR:", e)
    print(f"\n{len(pages)} page(s), {len(files)} tracked file(s): "
          + ("clean." if not errors else f"{len(errors)} error(s)."))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
