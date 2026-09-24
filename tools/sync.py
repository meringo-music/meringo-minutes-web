"""Writes shared fragments into every page, so they're defined once.

    python tools/sync.py           # rewrite the marker regions from partials/
    python tools/sync.py --check   # exit 1 if any page has drifted

A page marks a region with a pair of comments:

    <!-- sync:header -->
    <!-- /sync:header -->

and the region is replaced with partials/header.html. The output is committed,
because the site has no build step at serve time. tools/check.py runs --check,
so a page edited by hand inside a region fails the check.

Two regions are generated rather than copied, both from assets/data/faq.json:

    sync:faq      the /faq/ page's questions, grouped, as <details> elements
    sync:faq-ld   the same questions and answers as FAQPage JSON-LD

Both are built from the same plain text, and tools/check.py compares the
visible answers with the JSON-LD on the page itself.

Three more are generated from assets/data/demo.json, for the home page's demo:

    sync:demo-score    the scoreboard, counted from the audit notes (demo.js
                       counts again in the browser, from the same data)
    sync:demo          the app's summary and all 16 exchanges as plain text,
                       with my note on each flagged item: the demo without
                       JavaScript
    sync:demo-script   the script the voices read

tools/check.py also checks that every app string in demo.json appears in the
sync:demo region.

Every page must carry the header and footer regions.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTIALS = ROOT / "partials"
FAQ = ROOT / "assets" / "data" / "faq.json"
FACTS = ROOT / "data" / "facts.json"
REQUIRED = ("header", "footer")
REGION = re.compile(r"(?P<open>[ \t]*<!-- sync:(?P<name>[a-z0-9-]+) -->\n)(?P<body>.*?)(?P<close>[ \t]*<!-- /sync:(?P=name) -->)", re.S)
LINK = re.compile(r"\[([^\]]+)\]\((/[^)\s]*)\)")
EMAIL = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")


class FaqError(ValueError):
    """faq.json can't be rendered as written."""


def answer_plain(answer: str) -> str:
    """An answer as a reader sees it: [text](/path/) becomes text."""
    return LINK.sub(r"\1", answer)


def answer_html(entry: dict, facts: dict[str, str]) -> str:
    """The answer as HTML. Each number listed in the entry's `facts` (in
    reading order) becomes <span data-fact>, each quotation in `app` sits in
    data-lint="app", and a [text](/path/) link or an email address becomes a
    link. Its text content is exactly answer_plain(), which the JSON-LD carries."""
    raw, eid = entry["answer"], entry["id"]
    spans: list[tuple[int, int, str, str]] = []  # (start, end, open tag, close tag), in plain-text offsets

    def free(start: int, end: int) -> bool:
        return not any(s < end and start < e for s, e, _, _ in spans)

    removed = 0
    for m in LINK.finditer(raw):
        start = m.start() - removed
        spans.append((start, start + len(m.group(1)), f'<a href="{html.escape(m.group(2))}">', "</a>"))
        removed += len(m.group(0)) - len(m.group(1))
    plain = answer_plain(raw)

    cursor = 0
    for fid in entry.get("facts", []):
        if fid not in facts:
            raise FaqError(f"{eid}: fact {fid} is not in data/facts.json")
        rx = re.compile(r"(?<![\w.])" + re.escape(facts[fid]) + r"(?![\w%]|\.\d)")
        m = rx.search(plain, cursor)
        if not m:
            raise FaqError(f'{eid}: fact {fid} ("{facts[fid]}") is not in the answer after character {cursor}')
        spans.append((m.start(), m.end(), f'<span data-fact="{fid}">', "</span>"))
        cursor = m.end()

    for quote in entry.get("app", []):
        start = plain.find(quote)
        while start != -1 and not free(start, start + len(quote)):
            start = plain.find(quote, start + 1)
        if start == -1:
            raise FaqError(f"{eid}: app quotation not found clear of other markup: {quote}")
        spans.append((start, start + len(quote), '<span data-lint="app">', "</span>"))

    for m in EMAIL.finditer(plain):
        if free(m.start(), m.end()):
            spans.append((m.start(), m.end(), f'<a href="mailto:{m.group(0)}">', "</a>"))

    spans.sort()
    out, pos = [], 0
    for start, end, open_, close in spans:
        out += [html.escape(plain[pos:start], quote=False), open_, html.escape(plain[start:end], quote=False), close]
        pos = end
    out.append(html.escape(plain[pos:], quote=False))
    return "".join(out)


def load_faq() -> tuple[dict, dict[str, str]]:
    data = json.loads(FAQ.read_text(encoding="utf-8"))
    facts = {f["id"]: str(f["value"]) for f in json.loads(FACTS.read_text(encoding="utf-8"))["facts"]}
    known = {g["id"] for g in data["groups"]}
    for e in data["entries"]:
        if e["group"] not in known:
            raise FaqError(f"{e['id']}: unknown group {e['group']}")
    return data, facts


def render_faq() -> str:
    """The sync:faq region: a topic list, then each group's questions."""
    data, facts = load_faq()
    groups = [g for g in data["groups"] if any(e["group"] == g["id"] for e in data["entries"])]
    ind = "    "
    lines = [f'{ind}<nav class="faq-topics" aria-label="Topics">', f"{ind}  <ul>"]
    lines += [f'{ind}    <li><a href="#topic-{g["id"]}">{html.escape(g["label"])}</a></li>' for g in groups]
    lines += [f"{ind}  </ul>", f"{ind}</nav>"]
    for g in groups:
        lines += ["", f'{ind}<section class="faq-group" aria-labelledby="topic-{g["id"]}">',
                  f'{ind}  <h2 id="topic-{g["id"]}">{html.escape(g["label"])}</h2>']
        for e in (e for e in data["entries"] if e["group"] == g["id"]):
            lines += [f'{ind}  <details class="faq-item" id="{e["id"]}">',
                      f'{ind}    <summary>{html.escape(e["q"], quote=False)}</summary>',
                      f"{ind}    <p>{answer_html(e, facts)}</p>",
                      f"{ind}  </details>"]
        lines.append(f"{ind}</section>")
    return "\n".join(lines) + "\n"


def faq_jsonld() -> dict:
    """FAQPage structured data, in the page's own order of questions."""
    data, _ = load_faq()
    order = [g["id"] for g in data["groups"]]
    entries = sorted(data["entries"], key=lambda e: order.index(e["group"]))
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": e["q"],
             "acceptedAnswer": {"@type": "Answer", "text": answer_plain(e["answer"])}}
            for e in entries
        ],
    }


def render_faq_ld() -> str:
    """The sync:faq-ld region. '</' is escaped so no answer can close the script."""
    body = json.dumps(faq_jsonld(), ensure_ascii=False, indent=2).replace("</", "<\\/")
    lines = ['  <script type="application/ld+json">', *("  " + line for line in body.splitlines()), "  </script>"]
    return "\n".join(lines) + "\n"


DEMO = ROOT / "assets" / "data" / "demo.json"


def demo_module():
    sys.path.insert(0, str(ROOT / "tools" / "demo"))
    import build_demo  # noqa: E402
    return build_demo


def load_demo() -> dict:
    return json.loads(DEMO.read_text(encoding="utf-8"))


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def render_demo_score() -> str:
    """The scoreboard's lines, each number in <b data-tally> for demo.js."""
    demo = load_demo()
    counts = demo_module().tally(demo)
    ind = " " * 10
    lines = [f'{ind}<ul class="score-list">']
    for template in demo["site"]["captions"]["score"]:
        body = re.sub(r"\{(\w+)\}", lambda m: f'<b data-tally="{m.group(1)}">{counts[m.group(1)]}</b>', esc(template))
        lines.append(f"{ind}  <li>{body}</li>")
    lines.append(f"{ind}</ul>")
    return "\n".join(lines) + "\n"


def render_demo() -> str:
    """The demo as plain text: the app's words in data-lint="app", my note
    after each item that has one."""
    demo = load_demo()
    bd = demo_module()
    app, site = demo["app"], demo["site"]
    cap, audit, chrome = site["captions"], site["audit"], app["chrome"]
    ind = " " * 10

    def note(h: str, quote: str | None = None) -> str:
        a = audit.get(h)
        if not a or not a.get("note"):
            return ""
        q = f'“{" ".join(quote.split(" ")[:5])}…” ' if quote else ""
        return f'<p class="audit-static"><strong>{esc(cap["auditBy"] + " · " + q + bd.verdict_text(a, cap))}.</strong> {esc(a["note"])}</p>'

    s = app["summary"]
    out = [f'{ind}<div class="demo-text">',
           f'{ind}  <h3 data-lint="app">{esc(s["heading"])}</h3>',
           f'{ind}  <p data-lint="app">{esc(s["overview"])}</p>{note(s["overviewH"])}']
    for sec in s["sections"]:
        out.append(f'{ind}  <h4 data-lint="app">{esc(sec["heading"])}</h4>')
        if not sec["items"]:
            continue
        out.append(f"{ind}  <ul>")
        for it in sec["items"]:
            words = [f'<strong>{esc(it["label"])}</strong>:']
            for x in it["sentences"]:
                words.append(esc(x["text"]) + (f' <span class="ts">{esc(x["t"])}</span>' if x["show"] else ""))
            many = len(it["sentences"]) > 1
            notes = "".join(note(x["h"], x["text"] if many else None) for x in it["sentences"])
            out.append(f'{ind}    <li><p data-lint="app">{" ".join(words)}</p>{notes}</li>')
        out.append(f"{ind}  </ul>")
    out += [f'{ind}  <h4 data-lint="app">{esc(chrome["setAsideHeading"])}</h4>',
            f'{ind}  <p data-lint="app">{esc(chrome["setAsideLine"])}</p>',
            f"{ind}  <ul>"]
    for it in app["setAside"]:
        label = f'<strong>{esc(it["label"])}</strong>: ' if it["label"] else ""
        out.append(f'{ind}    <li><p data-lint="app">{label}{esc(it["text"])}</p>{note(it["h"])}</li>')
    out += [f"{ind}  </ul>", f'{ind}  <h3>{esc(cap["questions"])}</h3>', f'{ind}  <ol class="exchanges">']
    for q in app["asks"]:
        body = []
        for x in q["answer"]:
            body.append(f'<p>{esc(x["text"])}</p>')
            body += [f'<p class="ask-cite"><span class="ts">{esc(c["t"])}</span> {esc(c["speaker"])}: {esc(c["text"])}</p>' for c in x["cites"]]
        if q["footnote"]:
            body.append(f'<p class="ask-foot">{esc(q["footnote"])}</p>')
        out.append(f'{ind}    <li><p class="q" data-lint="app"><strong>{esc(q["q"])}</strong></p>'
                   f'<div data-lint="app">{"".join(body)}</div>{note(q["h"])}</li>')
    out += [f"{ind}  </ol>", f"{ind}</div>"]
    return "\n".join(out) + "\n"


def render_demo_script() -> str:
    ind = " " * 10
    lines = [f'{ind}<ol class="script" data-lint="reference">']
    lines += [f'{ind}  <li><strong>{esc(l["speaker"])}:</strong> {esc(l["text"])}</li>'
              for l in load_demo()["reference"]["script"]]
    lines.append(f"{ind}</ol>")
    return "\n".join(lines) + "\n"


GENERATED = {"faq": render_faq, "faq-ld": render_faq_ld,
             "demo-score": render_demo_score, "demo": render_demo, "demo-script": render_demo_script}


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
        if name in GENERATED:
            try:
                return m.group("open") + GENERATED[name]() + m.group("close")
            except (FaqError, KeyError, ValueError) as e:
                problems.append(f"sync:{name} can't be generated: {e}")
                return m.group(0)
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
            errors.append(f"{rel}: a shared or generated region differs from its source (run python tools/sync.py)")
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
