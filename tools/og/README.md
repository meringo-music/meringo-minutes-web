# The Open Graph image

`og.html` and `og.css` lay out the 1200 × 630 card that link previews show for every page
(`og:image`, and `twitter:card` `summary_large_image`). The render is committed as
`assets/img/og.png`; nothing builds it at serve time.

The card uses only this site's own files: the self-hosted fonts, the app icon, and the
day-rate exchange re-set as text, word for word as on the home page.

## Rendering it

Serve the repo root, so the root-absolute `/assets/fonts/` and `/tools/og/` paths resolve:

    python -m http.server 8099 --bind 127.0.0.1

Then, from the repo root in another shell, with a throwaway profile so no extension or
setting of yours reaches the render:

    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
      --headless=new --disable-gpu --hide-scrollbars --disable-extensions --no-proxy-server \
      --user-data-dir="$(mktemp -d)" \
      --window-size=1200,630 --force-device-scale-factor=1 \
      --screenshot="$PWD/assets/img/og.png" \
      http://127.0.0.1:8099/tools/og/og.html

- `--disable-extensions` and `--no-proxy-server`: an extension installed by policy, or a
  filtering proxy, can repaint the page before the screenshot is taken.
- `--force-device-scale-factor=1` keeps the file at exactly 1200 × 630.

Look at the PNG before committing it. If the headline or the answer changes on the home
page, change it here too and render again; the `og:image:alt` text on every page says what
the card shows.
