# meringo-minutes-web

Source for **https://meringominutes.app**, the website for Meringo Minutes™, a
Meringo Labs meeting recorder for the Mac.

It's a static site with no build step, deployed by GitHub Pages from `main`.
`DEPLOY.md` covers hosting, DNS and the launch states.

```
index.html · 404.html      pages (each page is a folder with its own index.html)
assets/css/site.css        the one stylesheet: tokens for both themes, all components
assets/fonts/              Cormorant Garamond and Inter (woff2, self-hosted; OFL.txt)
assets/img/                app icon, Meringo mark
tools/check.py             copy rules, links, CSP, launch state (run before every PR)
tools/lint_rules.json      the copy rules check.py enforces, each with its reason
tools/shoot.mjs            screenshots at real device widths, in light and dark
```

The site loads nothing from any other origin. Every page carries a
Content-Security-Policy that says so, and `tools/check.py` fails any page that
doesn't.

© 2026 Meringo Labs LLC
