# Deployment and release boundary

## Current status: hardened preview, not sealed publication

The web application is a static preview. It performs no runtime AI inference and
does not require a server-side calculation service.

Both supported hosts currently build from mutable files under `web/src`. They do
**not** deploy an immutable directory from `receipts/<slug>/<year>/<revision>/`.
Consequently, a successful deployment proves that tests and the current bridge
validators passed; it does not prove that the deployed bytes are a sealed pack.

The existing bridge seal also does not yet bind every source PDF, extract,
extractor version, dependency manifest, or public-only projection. Do not label a
site **Sealed** or **Published** until the full requirements in `PUBLISH.md` are
implemented and the production response bytes are checked against that manifest.

Every current deployment must therefore display **Preview** and remain
`noindex`. Publication additionally requires a named publisher, correction
contact, source/licence review, and an immutable rollback target.

## Automated GitHub Pages preview

`.github/workflows/deploy-pages.yml` is the only repository-defined automatic
deployment:

- A push to the repository's current default branch, or a manual run whose
  selected ref is that default branch, may deploy.
- Feature branches cannot deploy, including through `workflow_dispatch`.
- The validation/build job has read-only repository access.
- Pages and OIDC permissions exist only in the deployment job.
- Third-party Actions are pinned to verified commit SHAs.
- Python tests, the locked regional registry, every non-template pack, web tests,
  the production build, and a production-dependency audit must pass first.
- The checked public-pack projection must match its source data; internal
  ledgers and blocked packs are not accepted as browser artifacts.
- Pack validators run in explicit `--no-write` mode, followed by a clean-tree
  assertion that catches accidental evidence or timestamp rewrites.
- Production deployments are serialized rather than cancelled mid-release.

Configure the `github-pages` environment in repository settings so that only
the current default branch may deploy, with required reviewers, before treating
the URL as externally managed.
GitHub Pages does not interpret Cloudflare's `_headers` format, so response-header
enforcement must be verified separately if GitHub Pages becomes a long-term host.
On GitHub Pages, only the HTML `noindex` and `no-referrer` metadata from this
repository apply; CSP, HSTS, frame protection, and Permissions Policy are not
enforced by `_headers`. Treat Pages as a preview host, not the hardened
publication host.

## Cloudflare Workers static-assets preview

Current account preview:
`https://tax-receipt-prototype.jstn0513.workers.dev/`

`wrangler.jsonc` serves `web/dist`, not the Vite source directory. It explicitly
disables persistent Workers Logs. `web/public/_headers` supplies CSP,
clickjacking, MIME-sniffing, permissions, referrer, transport, and preview
indexing controls, and Vite copies it to `web/dist` during a build.

Use a narrowly scoped Cloudflare API token stored outside the repository. The
token should be limited to the intended account and Workers script. Never put it
in `wrangler.jsonc`, a committed environment file, or command history.

The current exact audited Wrangler release is `4.114.0`. Until Wrangler is added
to the project lockfile, use that explicit version instead of an unversioned
`npx wrangler`:

```powershell
$ErrorActionPreference = "Stop"
$WranglerVersion = "4.114.0"

python -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency install failed" }

python -m unittest discover -s tests -p "*test*.py"
if ($LASTEXITCODE -ne 0) { throw "Python tests failed" }

python scripts/validate_regional_registry.py
if ($LASTEXITCODE -ne 0) { throw "Regional registry validation failed" }

python scripts/build_public_packs.py --check
if ($LASTEXITCODE -ne 0) { throw "Public pack projection drifted" }

Get-ChildItem corpus -Directory |
  Where-Object {
    -not $_.Name.StartsWith("_") -and
    (Test-Path (Join-Path $_.FullName "pack.yaml"))
  } |
  ForEach-Object {
    python scripts/validate_pack.py $_.Name --no-write
    if ($LASTEXITCODE -ne 0) { throw "Pack validation failed: $($_.Name)" }
  }

npm --prefix web ci --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "Web dependency install failed" }
npm --prefix web test -- --run
if ($LASTEXITCODE -ne 0) { throw "Web tests failed" }
npm --prefix web audit --omit=dev --audit-level=high
if ($LASTEXITCODE -ne 0) { throw "Production dependency audit failed" }
npm --prefix web run build
if ($LASTEXITCODE -ne 0) { throw "Web build failed" }
npx --yes "wrangler@$WranglerVersion" deploy --dry-run
if ($LASTEXITCODE -ne 0) { throw "Wrangler dry run failed" }
npx --yes "wrangler@$WranglerVersion" deploy
if ($LASTEXITCODE -ne 0) { throw "Cloudflare deploy failed" }
```

The local `scripts/deploy_preview.ps1` helper remains a preview convenience and
currently invokes an unpinned Wrangler command. Do not use that helper as an
unattended production release until it consumes the project-locked Wrangler
binary.

After deployment, verify the response rather than trusting the command's exit
code:

```powershell
$PreviewUrl = "https://tax-receipt-prototype.jstn0513.workers.dev/"
$Response = Invoke-WebRequest -Uri $PreviewUrl
$Response.StatusCode
$Response.Headers["Content-Security-Policy"]
$Response.Headers["X-Robots-Tag"]
$Response.Headers["Referrer-Policy"]
```

Expected: HTTP 200, a self-only content policy, `noindex, nofollow`, and
`no-referrer`.

## Local production-build preview

```powershell
npm --prefix web ci --ignore-scripts --no-audit --no-fund
npm --prefix web test -- --run
npm --prefix web run build
npm --prefix web run preview
```

Set `GITHUB_PAGES=true` only when testing the GitHub project-path build:

```powershell
$env:GITHUB_PAGES = "true"
npm --prefix web run build
npm --prefix web run preview
Remove-Item Env:GITHUB_PAGES
```

## Requirements for a future sealed deployment

A publication workflow must be separate from the current preview build and must:

1. Accept one existing sealed public artifact; never rebuild municipal data.
2. Verify the manifest against disk in both directions.
3. Verify locked source, extraction, engine, pack, dependency, and Git identities.
4. Confirm the artifact contains only the public projection and passes the PII
   denylist.
5. Upload those exact bytes to an immutable versioned URL.
6. Fetch the production copy and compare every response body hash with the
   manifest.
7. Record the publisher approval, canonical URL, deployed manifest hash, time,
   and rollback target.

Until all seven steps exist, release records and UI language must say **Preview**.

## Privacy and operational defaults

- No address, owner, roll number, account, or dispute text is collected.
- Assessment scenarios remain in the browser; only a display preference may be
  stored locally.
- There is no runtime AI, advertising, behavioural analytics, or tracking pixel.
- Cloudflare Workers Logs are disabled. Hosting providers may retain
  security/abuse records outside application control.
- External evidence links receive `Referrer-Policy: no-referrer`.
- The browser-facing notice is served at `<deployment-base>/privacy.txt`.
- Re-enable request logging only after documenting purpose, fields, retention,
  access, sampling, and deletion, and after ensuring URLs cannot contain personal
  data.

## Remaining supply-chain risk

The workflow pins GitHub Actions to immutable SHAs and Python dependencies to
exact versions. Python distribution hashes are not locked yet. The npm lockfile
remains authoritative for the web build and install lifecycle scripts are
disabled in CI.

Wrangler is not yet present in `web/package-lock.json`; the explicit version
above narrows but does not eliminate registry compromise risk. Add it as a locked
development dependency in a dedicated dependency-change review before creating
an automated Cloudflare production workflow.
