# meringo-minutes-web

Source for **https://meringominutes.app**, the website for Meringo Minutes™, a
Meringo Labs meeting recorder for the Mac.

It's a static site with no build step, deployed by GitHub Pages from `main`.
`DEPLOY.md` covers hosting, DNS and the launch states.

```
index.html · 404.html      pages (each page is a folder with its own index.html)
how-it-works/ privacy/ download/   content pages, <main class="page">; privacy/ is also the desk's page template
faq/                       the FAQ: its questions and FAQPage JSON-LD are generated from assets/data/faq.json
data/facts.json            every number in page copy, with its source, method and date
partials/                  header and footer, written into every page by tools/sync.py
assets/css/site.css        the one stylesheet: tokens for both themes, all components
assets/js/                 theme-init.js (before paint), site.js (theme toggle, current page), theme.js and nav.js (pure logic),
                           ask-core.js (the FAQ assistant's matching, no DOM) and ask-ui.js (the box on /faq/)
assets/data/faq.json       every FAQ entry: question, alternative phrasings, keywords, answer, sources; and the assistant's gates
assets/vendor/             MiniSearch 7.1.2, byte for byte, with its licence and SHA-256 (README.md there)
assets/fonts/              Cormorant Garamond and Inter (woff2, self-hosted; OFL.txt)
assets/img/                app icon, Meringo mark
tools/check.py             copy rules, links, CSP, launch state, sourced numbers, the desk template, shared regions, contrast
tools/sync.py              python tools/sync.py after editing partials/ or faq.json; --check for drift
tools/contrast.py          WCAG contrast of every colour token pair, both themes
tools/commit_lint.py       no AI attribution in commit messages (run by CI)
tools/lint_rules.json      the copy rules check.py enforces, each with its reason
tools/shoot.mjs            screenshots at real device widths, in light and dark
tests/                     node --test; faq-eval.json is the assistant's evaluation set (no wrong answers, in any bucket)
.github/workflows/         the checks, on every pull request and push to main
```


The site loads nothing from any other origin. Every page carries a
Content-Security-Policy that says so, and `tools/check.py` fails any page that
doesn't.

© 2026 Meringo Labs LLC
