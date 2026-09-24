# Deploying meringominutes.app

A static site with no build step, served by GitHub Pages from `main` at the
repo root. `.nojekyll` makes Pages serve the files exactly as they are in the
repo. `CNAME` holds the custom domain.

## Before every pull request

```powershell
python tools/check.py                    # copy rules, links, CSP, launch state, forbidden text
python -m http.server 8099 --bind 127.0.0.1
node tools/shoot.mjs shots /             # screenshots at 390/768/1280 in light and dark;
                                         # exits 1 if anything scrolls sideways
```

In Git Bash, run `node tools/shoot.mjs` with `MSYS_NO_PATHCONV=1` set, or it
rewrites `/` into a Windows path.

A merge to `main` is the publish. Nothing else deploys the site.

## One-time setup, in this order

### 1. Verify the domain for the account

Verifying first stops anyone else's Pages site from claiming the domain.

`meringo-music` is a personal GitHub account, not an organization, so the
verified domain lives in the account's own settings, not the repo's:

1. Signed in as **meringo-music**: profile picture → **Settings** → *Code, planning, and
   automation* → **Pages** → **Add a domain** → `meringominutes.app`.
2. GitHub shows a **TXT** record, host `_github-pages-challenge-meringo-music`, with a one-off
   value. Add it at Porkbun (step 2). Once DNS answers, press **Verify**.

### 2. Porkbun DNS

Porkbun → Domain Management → `meringominutes.app` → **DNS**.

First delete Porkbun's default **parking** records (the apex `A`/`ALIAS` and the
default `www`), and turn off **URL Forwarding** if it's on. Leave any MX/email
records alone.

Then add these, all with TTL 600:

| Type  | Host (Porkbun)  | Answer                     |
|-------|-----------------|----------------------------|
| TXT   | `_github-pages-challenge-meringo-music` | the value from step 1 |
| A     | *(blank)*       | `185.199.108.153`          |
| A     | *(blank)*       | `185.199.109.153`          |
| A     | *(blank)*       | `185.199.110.153`          |
| A     | *(blank)*       | `185.199.111.153`          |
| AAAA  | *(blank)*       | `2606:50c0:8000::153`      |
| AAAA  | *(blank)*       | `2606:50c0:8001::153`      |
| AAAA  | *(blank)*       | `2606:50c0:8002::153`      |
| AAAA  | *(blank)*       | `2606:50c0:8003::153`      |
| CNAME | `www`           | `meringo-music.github.io`  |

These are the same records meringo.app and meringolisten.app use. Check them:

```powershell
nslookup meringominutes.app        # the four 185.199.108-111.153 addresses
nslookup www.meringominutes.app    # meringo-music.github.io
```

### 3. Pages

Repo → **Settings → Pages**:

1. *Build and deployment* → **Deploy from a branch**, branch **`main`**, folder **`/ (root)`**.
2. **Custom domain** → `meringominutes.app`. This matches `CNAME`.
3. Wait for "DNS check successful", then tick **Enforce HTTPS**. `.app` domains
   only work over HTTPS, so the site isn't reachable until this is done.

**Removing and re-adding the custom domain** (for example, to make Pages retry
its certificate) needs branch protection lifted for a moment. Pages records the
domain by committing the `CNAME` file to `main` itself ("Delete CNAME", then
"Create CNAME"), and the protection rule in step 4 refuses a direct commit, even
GitHub's. Turn the rule off, remove and re-add the domain, check that both
commits landed and `CNAME` still reads `meringominutes.app`, then turn the rule
back on with the same settings.

### 4. Protect `main`

Repo → **Settings → Branches** → rule for `main`:

- **Require a pull request before merging**, with **0 required approvals**.
  One approval would lock a solo owner out of his own merges.
- **Include administrators.**
- **Require status checks to pass**, with the `check` job from
  `.github/workflows/check.yml`.

### 5. Confirm it's live

```powershell
curl -sI https://meringominutes.app/          # 200
curl -sI https://www.meringominutes.app/      # 301 to the apex
curl -sI https://meringominutes.app/nope/     # 404, served by 404.html
```

Then add `https://meringominutes.app` to Google Search Console as a new property
and submit `sitemap.xml`.

## Launch states

Every page's `<body>` carries `data-cta-state`. `tools/check.py` fails if two
pages disagree.

| State       | What visitors see |
|-------------|-------------------|
| `prelaunch` | Now. Not for sale; one mailto asks to be told at launch. There is no Buy, no Download, and no price markup beyond the stated plan. |
| `launch`    | Buy, through Paddle's hosted checkout, linked out. Download: the notarized DMG on Cloudflare R2, where the app's update feed also lives, with its SHA-256. Not GitHub Releases: the app's repository is private, so its releases cannot be downloaded. $79 with its published end date, and $99 struck through. |
| `live`      | $99. |

The `launch` markup arrives in its own pull request. Two things block it, and
neither is on the site side: the checking model's licence, and the trial and
licence code in the app.

When the update feed (Sparkle) ships in the app, `/privacy/` must describe it
in the same change.
