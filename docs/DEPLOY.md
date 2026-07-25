# Deploy (static)

## What “ready to deploy” means here

1. `python scripts/audit_citations.py` exits **0** (no wrong-page / not-found)
2. `python scripts/validate_pack.py north-dumfries-on` exits **0**
3. Optional: `python scripts/seal_pack.py north-dumfries-on N` writes `receipts/...`
4. `cd web && npm test -- --run && npm run build` succeed
5. GitHub Pages workflow publishes `web/dist`

This is a **sealed preview**, not a claim of municipal affiliation. Full “Published”
still requires the human steps in `PUBLISH.md` (publisher, contact, corrections surface).

## Enable Pages (one-time in GitHub)

1. Repo → **Settings → Pages**
2. Source: **GitHub Actions**
3. Push to a watched branch (see `.github/workflows/deploy-pages.yml`)
4. Site URL: `https://<user>.github.io/tax-receipt-prototype/`

## Local preview of the production build

```bash
cd web
set GITHUB_PAGES=true   # PowerShell: $env:GITHUB_PAGES='true'
npm run build
npm run preview
```

## Re-seal after data changes

```bash
python scripts/build_evidence_model.py
python scripts/audit_citations.py
python scripts/validate_pack.py north-dumfries-on
python scripts/seal_pack.py north-dumfries-on 2   # bump revision; never overwrite
```
