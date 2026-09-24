"""Builds the home page demo from a Meringo Minutes capture.

    python tools/demo/build_demo.py --capture <capture folder>          # write
    python tools/demo/build_demo.py --capture <capture folder> --check  # diff only

Writes assets/data/demo.json and copies the recording byte for byte to
assets/demo/weekly-partners-meeting.m4a, refusing it unless its SHA-256 is
the one the capture recorded. Standard library only.

demo.json keeps three kinds of text apart:
  app        the app's own words, each one verbatim in a capture file or, for
             words that exist only on screen, in tools/demo/chrome.json with
             the frame it was read from;
  reference  the script the synthetic voices read ("what was actually said");
  site       my audit notes and captions, from tools/demo/annotations.json.

What it reads, and nothing else:
  - the "Summary with Timestamps" export, the only file with an anchor per
    sentence;
  - the transcript export, as the app printed it (mishearings included);
  - two fields of the meeting file: summaryUnverified (the set-aside card)
    and summaryCheck without its model field;
  - ASK-BANK.md, parsed strictly: the build fails if its layout drifts;
  - logs/ask-ax-dumps/index.log, for each question exactly as typed;
  - the recording, copied, never decoded;
  - the script, beside the capture in ../demo-meeting/transcript.txt.

It follows the app's display rules: inside one bullet, an anchor that repeats
an earlier one is not shown, and the empty "Open Questions & Next Steps"
heading is kept, as the app keeps it.

Every annotation is keyed to the SHA-256 of the exact app string it describes
(key_of() below), so a new capture with different words fails the build until
the notes are re-audited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "data" / "demo.json"
AUDIO_OUT = ROOT / "assets" / "demo" / "weekly-partners-meeting.m4a"
AUDIO_URL = "/assets/demo/weekly-partners-meeting.m4a"
AUDIO_SHA256 = "05d0f08bc2a70b13fd342b50576b3480c726d33100a8b66b0496aedf66e91301"
AUDIO_BYTES = 3_532_399

MEETING = "316E7F34-F77A-4327-AF02-1682F1AE7D34"
SOURCES = {  # key -> path inside the capture folder
    "export": "data/exports/Weekly partners meeting Summary with Timestamps.md",
    "transcript": "data/exports/Weekly partners meeting Transcript.txt",
    "meeting": f"data/app-files/final-after-asks/Meetings/{MEETING}.json",
    "askbank": "ASK-BANK.md",
    "typed": "logs/ask-ax-dumps/index.log",
    "audio": f"data/app-files/final-after-asks/Recordings/{MEETING}.m4a",
}
SCRIPT = "../demo-meeting/transcript.txt"  # relative to the capture folder
BUILD = {"version": "1.1.0 (3)", "commit": "ec526a2", "captured": "2026-09-23"}
CHECK_FIELDS = ("claims", "supported", "recovered")  # summaryCheck, never its model
VERDICTS = {"yes", "partly", "no"}

TS = r"\d{1,2}:\d\d"


class BuildError(Exception):
    """The capture can't be turned into demo.json as it stands."""


def fail(msg: str):
    raise BuildError(msg)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_of(text: str) -> str:
    """The key an annotation is filed under: SHA-256 of the exact app string."""
    return sha256(text.encode("utf-8"))


def seconds(ts: str) -> int:
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def ask_string(ask: dict) -> str:
    """One exchange as the app shows it, one line each: the question, then each
    answer sentence followed by its citation rows, then the footnote."""
    lines = [ask["q"]]
    for sentence in ask["answer"]:
        lines.append(sentence["text"])
        lines += [f'{c["t"]} {c["speaker"]}: {c["text"]}' for c in sentence["cites"]]
    if ask["footnote"]:
        lines.append(ask["footnote"])
    return "\n".join(lines)


def app_items(app: dict) -> list[tuple[str, str, str]]:
    """(kind, where, exact app string) for everything an annotation can describe."""
    out = [("summary", "overview", app["summary"]["overview"])]
    for sec in app["summary"]["sections"]:
        for item in sec["items"]:
            for s in item["sentences"]:
                out.append(("summary", f'{sec["heading"]} / {item["label"]}', s["text"]))
    for item in app["setAside"]:
        out.append(("setAside", item["label"] or "overview", item["text"]))
    for ask in app["asks"]:
        out.append(("ask", f'Q{ask["n"]}', ask_string(ask)))
    return out


def tally(demo: dict) -> dict[str, int]:
    """The scoreboard, counted from the audit notes. The same arithmetic as
    tally() in assets/js/demo-core.js; tests/demo-bank.test.js holds the two
    to the same numbers."""
    audit, app = demo["site"]["audit"], demo["app"]
    kept = [audit[app["summary"]["overviewH"]]] + [
        audit[s["h"]] for sec in app["summary"]["sections"] for it in sec["items"] for s in it["sentences"]]
    anchored = [a for a in kept if a["line"] is not None]
    asks = [{**audit[q["h"]], "refused": q["refused"]} for q in app["asks"]]
    traps = [a for a in asks if not a["answerable"]]
    answerable = [a for a in asks if a["answerable"]]
    n = lambda xs, test: sum(1 for x in xs if test(x))
    return {
        "lineNo": n(anchored, lambda a: a["line"] == "no"),
        "anchored": len(anchored),
        "linePartly": n(anchored, lambda a: a["line"] == "partly"),
        "keptPartly": n(kept, lambda a: a["transcript"] == "partly"),
        "kept": len(kept),
        "trapsRefused": n(traps, lambda a: a["refused"]),
        "traps": len(traps),
        "answerableRefused": n(answerable, lambda a: a["refused"]),
        "answerable": len(answerable),
        "invented": n(asks, lambda a: a.get("invented")),
    }


def verdict_text(a: dict, cap: dict) -> str:
    """As verdictText() in assets/js/demo-core.js."""
    if "verdict" in a:
        parts = [f'{cap["verdict"]}: {a["verdict"]}', a.get("label")]
    else:
        parts = [a["line"] is not None and f'{cap["line"]}: {a["line"]}', f'{cap["transcript"]}: {a["transcript"]}']
    return " · ".join(p for p in parts if p)


# ─── Parsers ────────────────────────────────────────────────────────────────

BULLET = re.compile(r"^\* \*\*(?P<label>[^*]+)\*\*: (?P<rest>.+)$")


def parse_export(text: str) -> dict:
    """The timestamped summary export: overview, sections, anchored sentences."""
    body = text
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end < 0:
            fail("export: front matter never closes")
        body = body[end + 5:]
    lines = body.lstrip("\n").split("\n")
    if not lines or lines[0] != "# Meeting Summary":
        fail(f"export: expected '# Meeting Summary' first, found {lines[:1]}")
    overview: list[str] = []
    sections: list[dict] = []
    for raw in lines[1:]:
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            sections.append({"heading": line[3:], "items": []})
            continue
        if not sections:
            overview.append(line)
            continue
        m = BULLET.match(line)
        if not m:
            fail(f"export: a line in '{sections[-1]['heading']}' is not a '* **Label**: text `m:ss`' bullet: {line[:80]}")
        parts = re.split(rf"\s*`({TS})`\s*", m.group("rest"))
        if len(parts) < 3 or parts[-1] != "":
            fail(f"export: a sentence has no anchor after it: {line[:80]}")
        sentences, seen = [], set()
        for i in range(0, len(parts) - 1, 2):
            text_, ts = parts[i].strip(), parts[i + 1]
            if not text_:
                fail(f"export: an anchor with no sentence before it: {line[:80]}")
            # The app's display rule: a repeated anchor in one bullet isn't shown.
            sentences.append({"text": text_, "t": ts, "show": ts not in seen})
            seen.add(ts)
        sections[-1]["items"].append({"label": m.group("label"), "sentences": sentences})
    if len(overview) != 1:
        fail(f"export: expected one overview paragraph, found {len(overview)}")
    if not sections:
        fail("export: no sections")
    return {"heading": "Meeting Summary", "overview": overview[0], "sections": sections}


LINE = re.compile(r"^\[(\d\d):(\d\d)\] ([^:\]]+): (.+)$")


def parse_transcript(text: str) -> list[dict]:
    out = []
    for n, raw in enumerate(text.split("\n"), 1):
        if not raw.strip():
            continue
        m = LINE.match(raw.rstrip())
        if not m:
            fail(f"transcript: line {n} is not '[mm:ss] Name: text': {raw[:80]}")
        mm, ss, speaker, said = m.groups()
        out.append({"t": f"{mm}:{ss}", "s": int(mm) * 60 + int(ss), "speaker": speaker, "text": said})
    if len({l["s"] for l in out}) != len(out):
        fail("transcript: two lines share a start time; anchors would be ambiguous")
    return out


def parse_set_aside(text: str) -> list[dict]:
    items = []
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        if raw.startswith("* "):
            m = BULLET.match(raw)
            if not m:
                fail(f"summaryUnverified: a bullet without a **Label**: {raw[:80]}")
            items.append({"label": m.group("label"), "text": m.group("rest")})
        elif items:
            fail(f"summaryUnverified: a paragraph after the bullets: {raw[:80]}")
        else:
            items.append({"label": None, "text": raw})
    return items


def section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        fail(f"ASK-BANK.md: no '## {title}' section")
    return m.group(1)


QUOTE_CITE = re.compile(rf"^> - `({TS})` ([^:]+): (.+)$")
FOOTNOTE_NONE = re.compile(r"^\*\*Footnote:\*\* none\.")
FOOTNOTE_TEXT = re.compile(r'^\*\*Footnote:\*\* "(.+?)"')


def parse_ask_bank(text: str) -> list[dict]:
    """The 16 exchanges. Answerable ones are headed '### N. question' with the
    answer as a block quote; traps are rows of one table. Anything else is a
    format change, and the build stops."""
    asks: list[dict] = []
    answerable = section(text, "Answerable")
    blocks = re.split(r"^### ", answerable, flags=re.M)[1:]
    if len(blocks) != 8:
        fail(f"ASK-BANK.md: expected 8 answerable questions, found {len(blocks)}")
    for block in blocks:
        lines = block.split("\n")
        m = re.fullmatch(r"(\d+)\. (.+)", lines[0])
        if not m:
            fail(f"ASK-BANK.md: bad question heading: {lines[0][:80]}")
        n, q = int(m.group(1)), m.group(2)
        if lines[1] != "**Answer**":
            fail(f"ASK-BANK.md Q{n}: '**Answer**' must follow the heading")
        quote = []
        i = 2
        while i < len(lines) and lines[i].startswith(">"):
            quote.append(lines[i])
            i += 1
        if not quote:
            fail(f"ASK-BANK.md Q{n}: no quoted answer")
        answer, footnote_q = [], None
        for line in quote:
            if line == ">":
                continue
            c = QUOTE_CITE.match(line)
            if c:
                if not answer:
                    fail(f"ASK-BANK.md Q{n}: a citation row before any sentence")
                answer[-1]["cites"].append({"t": c.group(1), "speaker": c.group(2), "text": c.group(3)})
            elif re.fullmatch(r"> \*[^*].*\*", line):
                footnote_q = line[3:-1]
            elif line.startswith("> ") and not line.startswith("> -"):
                if footnote_q:
                    fail(f"ASK-BANK.md Q{n}: a sentence after the footnote")
                answer.append({"text": line[2:], "cites": []})
            else:
                fail(f"ASK-BANK.md Q{n}: unrecognised line in the answer: {line[:80]}")
        rest = "\n".join(lines[i:]).strip().split("\n")[0]
        if FOOTNOTE_NONE.match(rest):
            footnote = None
        elif FOOTNOTE_TEXT.match(rest):
            footnote = FOOTNOTE_TEXT.match(rest).group(1)
        else:
            fail(f"ASK-BANK.md Q{n}: expected a '**Footnote:**' line after the answer, found: {rest[:80]}")
        if footnote != footnote_q:
            fail(f"ASK-BANK.md Q{n}: the footnote in the quote and the Footnote field disagree")
        asks.append({"n": n, "q": q, "answer": answer, "footnote": footnote})

    traps = section(text, "Traps (the honest answer is partly or wholly \"not in this meeting\")")
    rows = [l for l in traps.split("\n") if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|--")]
    if len(rows) != 8:
        fail(f"ASK-BANK.md: expected 8 trap rows, found {len(rows)}")
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) != 7 or not cells[0].isdigit():
            fail(f"ASK-BANK.md: a trap row doesn't have 7 cells: {row[:80]}")
        asks.append({"n": int(cells[0]), "q": cells[1], "answer": [{"text": cells[2], "cites": []}], "footnote": None})

    if [a["n"] for a in asks] != list(range(1, 17)):
        fail(f"ASK-BANK.md: questions should run 1 to 16 in order, found {[a['n'] for a in asks]}")
    return asks


def parse_typed(text: str) -> dict[int, str]:
    """logs/ask-ax-dumps/index.log: each question exactly as it was typed."""
    out = {}
    for m in re.finditer(r"^TAG=q(\d\d) typed=\[(.*?)\] ", text, re.M):
        out.setdefault(int(m.group(1)), m.group(2))
    return out


def parse_script(text: str) -> list[dict]:
    out = []
    for n, raw in enumerate(text.split("\n"), 1):
        if not raw.strip():
            continue
        m = re.match(r"^\[\d\d:\d\d\] ([^:]+): (.+)$", raw.rstrip())
        if not m:
            fail(f"script: line {n} is not '[mm:ss] Name: text': {raw[:80]}")
        # The script's own times are the writer's estimates, not the recording's;
        # they're dropped so nobody reads them as places in the audio.
        out.append({"speaker": m.group(1), "text": m.group(2)})
    return out


# ─── Annotations and chrome ─────────────────────────────────────────────────

def load_chrome(capture: Path) -> dict[str, str]:
    data = json.loads((HERE / "chrome.json").read_text(encoding="utf-8"))
    out = {}
    for name, entry in data["strings"].items():
        frame = capture / "screenshots" / entry["frame"]
        if not frame.is_file():
            fail(f"chrome.json: {name} cites frame {entry['frame']}, which isn't in the capture")
        out[name] = entry["text"]
    return out


def audit_entries(annotations: dict, app: dict) -> dict[str, dict]:
    """site.audit for demo.json: each annotation under the first 16 hex digits
    of its key, after checking that every key matches exactly one app string
    and every app string has exactly one annotation."""
    items = app_items(app)
    keys = {}
    for kind, where, text in items:
        k = key_of(text)
        if k in keys:
            fail(f"two app strings hash the same ({where}); annotations would be ambiguous")
        keys[k] = (kind, where)
    out: dict[str, dict] = {}
    for kind in ("summary", "asks"):
        for a in annotations[kind]:
            k = a["sha256"]
            if k not in keys:
                fail(f"annotations.json: {kind} entry {a.get('row') or a.get('n')} ({a.get('excerpt', '')[:40]}…) "
                     "matches no app string in this capture; re-audit it")
            short = k[:16]
            if short in out:
                fail(f"annotations.json: two entries for {keys[k][1]}")
            entry = {f: a[f] for f in ("line", "transcript", "verdict", "label", "note", "answerable", "invented") if f in a}
            for f in ("line", "transcript", "verdict"):
                if f in entry and entry[f] is not None and entry[f] not in VERDICTS:
                    fail(f"annotations.json: {keys[k][1]} {f} is {entry[f]!r}, not yes/partly/no")
            out[short] = entry
    missing = [where for kind, where, text in items if key_of(text)[:16] not in out]
    if missing:
        fail(f"annotations.json: no annotation for {missing}")
    return out


# ─── Build ──────────────────────────────────────────────────────────────────

def build(capture: Path, script_path: Path | None = None) -> tuple[dict, Path]:
    capture = capture.resolve()
    paths = {k: capture / v for k, v in SOURCES.items()}
    script_path = script_path or (capture / SCRIPT)
    for k, p in [*paths.items(), ("script", script_path)]:
        if not p.is_file():
            fail(f"{k}: {p.name} is not in the capture")

    raw = {k: p.read_bytes() for k, p in paths.items() if k != "audio"}
    text = {k: b.decode("utf-8") for k, b in raw.items()}
    audio = paths["audio"].read_bytes()
    if len(audio) != AUDIO_BYTES or sha256(audio) != AUDIO_SHA256:
        fail(f"audio: {len(audio)} bytes, SHA-256 {sha256(audio)}; expected {AUDIO_BYTES} and {AUDIO_SHA256}")

    summary = parse_export(text["export"])
    transcript = parse_transcript(text["transcript"])
    meeting = json.loads(text["meeting"])
    set_aside = parse_set_aside(meeting["summaryUnverified"])
    check = {f: meeting["summaryCheck"][f] for f in CHECK_FIELDS}  # the model field is never read out
    asks = parse_ask_bank(text["askbank"])
    typed = parse_typed(text["typed"])
    chrome = load_chrome(capture)
    script_bytes = script_path.read_bytes()
    script = parse_script(script_bytes.decode("utf-8"))

    # Cross-checks between the capture's own files
    by_time = {l["s"]: l for l in transcript}
    anchors = [s for sec in summary["sections"] for it in sec["items"] for s in it["sentences"]]
    for s in anchors:
        if seconds(s["t"]) not in by_time:
            fail(f"export: anchor {s['t']} is not the start of any transcript line")
    for ask in asks:
        if typed.get(ask["n"]) != ask["q"]:
            fail(f"ASK-BANK.md Q{ask['n']}: the question differs from what index.log says was typed: {typed.get(ask['n'])!r}")
        ask["refused"] = [s["text"] for s in ask["answer"]] == [chrome["askRefusal"]]
        for s in ask["answer"]:
            for c in s["cites"]:
                line = by_time.get(seconds(c["t"]))
                if not line or (line["speaker"], line["text"]) != (c["speaker"], c["text"]):
                    fail(f"ASK-BANK.md Q{ask['n']}: citation {c['t']} doesn't match the transcript line at that time")
        if ask["footnote"] and ask["footnote"] != chrome["askFootnote"]:
            fail(f"ASK-BANK.md Q{ask['n']}: a footnote chrome.json doesn't know")
    traced = int(re.match(r"All (\d+) claims", chrome["traced"]).group(1))
    if traced != len(anchors):
        fail(f"chrome.json says {traced} claims traced; the export anchors {len(anchors)} sentences")
    unverified = int(re.match(r"(\d+) unverified", chrome["setAsideHeading"]).group(1))
    if unverified != len(set_aside) or unverified != check["claims"] - check["supported"]:
        fail(f"chrome.json says {unverified} unverified; the meeting file has {len(set_aside)} set aside "
             f"and summaryCheck {check['claims']} - {check['supported']}")
    for kind, where, s in app_items({"summary": summary, "setAside": set_aside, "asks": asks}):
        if kind == "ask":
            continue
        home = text["export"] if kind == "summary" else meeting["summaryUnverified"]
        if s not in home:
            fail(f"{where}: not verbatim in its source: {s[:60]}")
    for ask in asks:
        for part in ask_string(ask).split("\n")[1:]:
            if part not in text["askbank"] and part.split(" ", 1)[-1] not in text["askbank"]:
                fail(f"Q{ask['n']}: not verbatim in ASK-BANK.md: {part[:60]}")

    app = {
        "title": chrome["title"],
        "chrome": chrome,
        "summary": summary,
        "setAside": set_aside,
        "check": check,
        "transcript": transcript,
        "asks": asks,
    }
    for s in anchors:
        s["h"] = key_of(s["text"])[:16]
    summary["overviewH"] = key_of(summary["overview"])[:16]
    for item in set_aside:
        item["h"] = key_of(item["text"])[:16]
    for ask in asks:
        ask["h"] = key_of(ask_string(ask))[:16]

    annotations = json.loads((HERE / "annotations.json").read_text(encoding="utf-8"))
    site = {"audit": audit_entries(annotations, app), "captions": annotations["captions"]}

    provenance = {
        "capture": capture.name,
        "app": BUILD,
        "audio": {"url": AUDIO_URL, "bytes": AUDIO_BYTES, "sha256": AUDIO_SHA256},
        "sources": [{"file": SOURCES[k], "sha256": sha256(b)} for k, b in raw.items()]
                   + [{"file": SOURCES["audio"], "sha256": sha256(audio)},
                      {"file": SCRIPT, "sha256": sha256(script_bytes)}],
    }
    demo = {
        "_about": "Generated by tools/demo/build_demo.py from a Meringo Minutes capture. Do not edit: "
                  "app is the app's own words, reference is the script, site is mine.",
        "provenance": provenance,
        "app": app,
        "reference": {"script": script},
        "site": site,
    }
    return demo, paths["audio"]


def dumps(demo: dict) -> str:
    return json.dumps(demo, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--capture", required=True, type=Path)
    ap.add_argument("--script", type=Path, help=f"default: <capture>/{SCRIPT}")
    ap.add_argument("--check", action="store_true", help="compare with the committed files; write nothing")
    args = ap.parse_args(argv)
    try:
        demo, audio = build(args.capture, args.script)
    except BuildError as e:
        print("ERROR:", e)
        return 1
    out = dumps(demo)
    if args.check:
        errors = []
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != out:
            errors.append("assets/data/demo.json differs from a fresh extraction of the capture (run build_demo.py)")
        if not AUDIO_OUT.is_file() or sha256(AUDIO_OUT.read_bytes()) != AUDIO_SHA256:
            errors.append("assets/demo/weekly-partners-meeting.m4a is not the capture's recording")
        for e in errors:
            print("ERROR:", e)
        if not errors:
            print("demo.json and the recording match the capture.")
        return 1 if errors else 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out, encoding="utf-8", newline="\n")
    AUDIO_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio, AUDIO_OUT)
    if sha256(AUDIO_OUT.read_bytes()) != AUDIO_SHA256:
        AUDIO_OUT.unlink()
        print("ERROR: the copied recording's SHA-256 is wrong; removed it")
        return 1
    n = len(demo["site"]["audit"])
    print(f"wrote assets/data/demo.json ({len(out.encode()):,} bytes, {n} annotations) and the recording ({AUDIO_BYTES:,} bytes, SHA-256 verified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
