# Deploy preview to Cloudflare Workers (jstn0513 account URL).
#
# Usage (PowerShell from repo root):
#   .\scripts\deploy_preview.ps1
#   .\scripts\deploy_preview.ps1 -Packs waterloo-on,kitchener-on
#
# Gate: validate_pack + audit hard-fails + vitest + vite build, then wrangler deploy.
# Target: https://tax-receipt-prototype.jstn0513.workers.dev/

param(
  [string[]]$Packs = @(
    "region-of-waterloo-on",
    "kitchener-on",
    "waterloo-on",
    "cambridge-on",
    "woolwich-on",
    "brant-county-on",
    "north-dumfries-on"
  ),
  [switch]$SkipTests,
  [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== validate packs ==" -ForegroundColor Cyan
foreach ($slug in $Packs) {
  $packPath = Join-Path $Root "corpus\$slug\pack.yaml"
  if (-not (Test-Path $packPath)) {
    Write-Host "skip missing pack $slug"
    continue
  }
  Write-Host "validate $slug"
  python scripts/validate_pack.py $slug
  if ($LASTEXITCODE -ne 0) {
    throw "validate_pack failed for $slug"
  }
}

if (-not $SkipTests) {
  Write-Host "== web tests + build ==" -ForegroundColor Cyan
  Push-Location (Join-Path $Root "web")
  try {
    npm test -- --run
    if ($LASTEXITCODE -ne 0) { throw "vitest failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "vite build failed" }
  } finally {
    Pop-Location
  }
}

if ($SkipDeploy) {
  Write-Host "SkipDeploy set — build gate passed; not deploying."
  exit 0
}

if (-not $env:CLOUDFLARE_API_TOKEN) {
  Write-Host @"
CLOUDFLARE_API_TOKEN is not set and this shell is non-interactive.
Run once in your terminal:
  npx wrangler login
or set CLOUDFLARE_API_TOKEN, then:
  npx wrangler deploy
Target: https://tax-receipt-prototype.jstn0513.workers.dev/
"@ -ForegroundColor Yellow
  exit 2
}

Write-Host "== wrangler deploy ==" -ForegroundColor Cyan
npx wrangler deploy
if ($LASTEXITCODE -ne 0) { throw "wrangler deploy failed" }

Write-Host "Deployed: https://tax-receipt-prototype.jstn0513.workers.dev/" -ForegroundColor Green
