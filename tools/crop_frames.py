"""Crops the capture's frames for the site. Crop and scale only, never retouch.

    python tools/crop_frames.py --capture <capture folder>

For each entry in tools/crops.json, crops the light and dark frame to the
entry's box, scales it to 1280 px wide, and writes
assets/img/frames/<name>-<theme>.webp and .png in sRGB (the PNG names only
that, in its profile) with no other metadata: the
frames carry EXIF, XMP and the capture display's own colour profile, which
names the display. Converting from that profile to sRGB keeps the colours as
they looked; it changes no pixel's meaning.

It refuses, and writes nothing:
  - frames 15a, 15b and 15c, whatever crops.json says: they show the checking
    model's name, and no crop removes it cleanly;
  - any other frame NOT-FOR-PUBLICATION.md lists as naming the checking model
    or showing a home-folder path (its sections 1 to 3), unless the entry's
    "clears" says what the crop removes. Look at the output before trusting it.
Frames the file lists only as "use with care" are printed as a reminder.

Needs Pillow (not used by CI; the output is committed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import io

from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parent.parent
CROPS = ROOT / "tools" / "crops.json"
OUT = ROOT / "assets" / "img" / "frames"
NEVER = ("15a-", "15b-", "15c-")


def listed(capture: Path) -> tuple[set[str], list[str]]:
    """(frames NOT-FOR-PUBLICATION.md forbids uncropped, its use-with-care lines)."""
    text = (capture / "NOT-FOR-PUBLICATION.md").read_text(encoding="utf-8")
    parts = re.split(r"^## (\d+)\. ", text, flags=re.M)
    forbidden, care = set(), []
    for number, body in zip(parts[1::2], parts[2::2]):
        if number in ("1", "2", "3"):
            forbidden |= set(re.findall(r"screenshots/([\w.-]+\.png)", body))
        elif number == "4":
            care = [l.strip("- ").strip() for l in body.splitlines() if l.startswith("- **")]
    if not forbidden:
        raise SystemExit("NOT-FOR-PUBLICATION.md: found no listed frames; its format may have changed")
    return forbidden, care


def refusals(entry: dict, forbidden: set[str]) -> list[str]:
    out = []
    for frame in entry["frames"].values():
        if frame.startswith(NEVER):
            out.append(f"{entry['name']}: {frame} is never published (it names the checking model and can't be cropped clean)")
        elif frame in forbidden and not entry.get("clears"):
            out.append(f"{entry['name']}: {frame} is listed in NOT-FOR-PUBLICATION.md; "
                       "give the crop a \"clears\" saying what it removes, and check the output")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crop the capture's frames for the site.")
    ap.add_argument("--capture", required=True, type=Path)
    ap.add_argument("--crops", type=Path, default=CROPS)
    args = ap.parse_args(argv)
    spec = json.loads(args.crops.read_text(encoding="utf-8"))
    forbidden, care = listed(args.capture)

    errors = [r for entry in spec["crops"] for r in refusals(entry, forbidden)]
    if errors:
        for e in errors:
            print("REFUSED:", e)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for entry in spec["crops"]:
        for theme, frame in entry["frames"].items():
            src = args.capture / "screenshots" / frame
            im = Image.open(src)
            left, top, right, bottom = entry["box"]
            if not (0 <= left < right <= im.width and 0 <= top < bottom <= im.height):
                print(f"REFUSED: {entry['name']}: box {entry['box']} is outside {frame} ({im.width} x {im.height})")
                return 1
            out = im.crop((left, top, right, bottom))
            if im.info.get("icc_profile"):
                display = ImageCms.ImageCmsProfile(io.BytesIO(im.info["icc_profile"]))
                out = ImageCms.profileToProfile(out, display, ImageCms.createProfile("sRGB"), outputMode=out.mode)
            width = spec["width"]
            out = out.resize((width, round(out.height * width / out.width)), Image.Resampling.LANCZOS)
            base = OUT / f"{entry['name']}-{theme}"
            out.save(base.with_suffix(".webp"), "WEBP", quality=82, method=6)
            out.save(base.with_suffix(".png"), "PNG", optimize=True)
            sizes = [base.with_suffix(s).stat().st_size for s in (".webp", ".png")]
            total += sizes[0]
            print(f"{base.relative_to(ROOT).as_posix()}.webp/.png  {out.width} x {out.height}  "
                  f"{sizes[0]:,} / {sizes[1]:,} bytes  from {frame}")
            # "01b" is covered by "01a–d"; "ask-06" and "(01:33)" are not frame 06 or 01
            number = re.escape(frame[:2])
            hits = [c for c in care if re.search(rf"(?<![\w-]){number}(?:[a-z](?:[–-][a-z])?)?(?![\w:])", c)]
            for c in hits:
                print(f"  use with care: {c}")
    print(f"{total:,} bytes of webp in all. Open every file and look for a path, a model name or anything personal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
