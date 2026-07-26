# Deploy (static)

## What “ready to deploy” means here

1. `python scripts/audit_citations.py` exits **0** (no wrong-page / not-found)
2. `python scripts/validate_pack.py north-dumfries-on` exits **0**
3. Optional: `python scripts/seal_pack.py north-dumfries-on N` writes `receipts/...`
4. `cd web && npm test -- --run && npm run build` succeed
5. A static host serves `web/dist`

This is a **sealed preview**, not a claim of municipal affiliation. Full “Published”
still requires the human steps in `PUBLISH.md` (publisher, contact, corrections surface).

---

## Cloudflare Workers (static assets) — your current `*.workers.dev` URL

Preview URL for this account: **https://tax-receipt-prototype.jstn0513.workers.dev/**

Local gated deploy (validate → tests → build → wrangler):

```powershell
# One-time: wrangler login   OR set CLOUDFLARE_API_TOKEN
.\scripts\deploy_preview.ps1
```

The blank page happened because Cloudflare was serving `web/` **source**
(`index.html` → `/src/main.tsx`) instead of the Vite **build** (`web/dist`).

If the log only shows `Executing user deploy command: npx wrangler deploy` and then
`web/dist` missing, the separate Build field was never run. Put everything in
**Deploy command**:

| Field | Value |
|---|---|
| **Build command** | leave empty (or same as deploy if required) |
| **Deploy command** | `npm --prefix web ci && npm --prefix web run build && npx wrangler deploy` |
| **Root directory** | `/` (repository root — where `wrangler.jsonc` lives) |
| **Branch** | `claude/citation-audit` |

`wrangler.jsonc` points assets at `./web/dist`. Do **not** set assets to `web`.

Save → **Retry deployment**. The log must show `vite build` **before** wrangler.
### Prefer Cloudflare Pages instead?

Same build, no wrangler:

| Field | Value |
|---|---|
| Root directory | `web` |
| Build command | `npm ci && npm run build` |
| Output directory | `dist` |

---

## Recommended: Cloudflare Pages (private repo OK)

**ToS / policy:** This is a normal, supported use. Cloudflare Pages free tier may deploy
**private or public** GitHub repos after you authorize the Cloudflare GitHub App for that
repo only. You are hosting *your* static build of public budget citations — not scraping
Cloudflare, not reselling their service, not violating GitHub’s terms by granting the App
access you control. Keep secrets out of the repo (FIR zips stay gitignored).

You do **not** need to make the GitHub repo public, and you do **not** need GitHub Enterprise.

### One-time setup

1. Open [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. Authorize **GitHub**; grant access to **only** `tax-receipt-prototype` (recommended)
3. Select branch: `claude/citation-audit` (or `main` once you merge)
4. Build settings:

| Field | Value |
|---|---|
| Framework preset | Vite (or None) |
| Root directory | `web` |
| Build command | `npm ci && npm run build` |
| Build output directory | `dist` |
| Environment variables | *(none required)* — do **not** set `GITHUB_PAGES` |

5. Deploy. URL will look like: `https://<project-name>.pages.dev`

**Important:** Leave `GITHUB_PAGES` unset. That flag is only for GitHub project Pages
(`base = /tax-receipt-prototype/`). Cloudflare serves from `/`.

### Netlify (same idea)

1. [app.netlify.com](https://app.netlify.com) → Add new site → Import from Git → GitHub  
2. Same root `web`, build `npm ci && npm run build`, publish `dist`  
3. Private repos are supported on the free tier with GitHub OAuth  

---

## Alternative: GitHub Pages (requires public repo on free accounts)

Free personal GitHub accounts cannot enable Pages on **private** repos (“Upgrade or make
this repository public”).

If you later make the repo public:

1. Repo → **Settings → Pages** → Source: **GitHub Actions**
2. Workflow: `.github/workflows/deploy-pages.yml` (sets `GITHUB_PAGES=true`)
3. URL: `https://<user>.github.io/tax-receipt-prototype/`

---

## Local preview of the production build

```bash
cd web
npm run build          # Cloudflare/Netlify-compatible (base /)
npm run preview
```

GitHub Pages local check only:

```bash
cd web
$env:GITHUB_PAGES='true'   # PowerShell
npm run build
npm run preview
```

## Re-seal after data changes

```bash
python scripts/build_evidence_model.py
python scripts/audit_citations.py
python scripts/validate_pack.py north-dumfries-on
python scripts/seal_pack.py north-dumfries-on N   # bump revision; never overwrite
```
