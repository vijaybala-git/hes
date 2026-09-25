<#
.SYNOPSIS
  Publish the WhyWatt? HEX architecture explainer to the GitHub Pages repo (www.whywatt.org).

.DESCRIPTION
  docs/explainer in THIS repo is the source of truth. This script mirrors it into
  <PagesRepo>/explainer, then (with -Push) commits and pushes the Pages repo.
  Only the explainer/ subfolder is touched -- index.html, presentations/, CNAME etc. in the
  Pages repo are left alone.

  Before publishing, refresh the data snapshots if any source data changed:
    .venv\Scripts\python.exe scripts\build_explainer_data.py

.PARAMETER PagesRepo
  Path to the local clone of vijaybala-git.github.io. Default: D:\vijay\Documents\whywatt

.PARAMETER Push
  Actually commit and push to origin/main. Without this flag the script does a dry run
  (mirror + show git status) and does NOT commit or push.

.EXAMPLE
  # Preview what would change, no push:
  powershell -ExecutionPolicy Bypass -File scripts\publish-explainer.ps1

  # Mirror, commit, and push live:
  powershell -ExecutionPolicy Bypass -File scripts\publish-explainer.ps1 -Push
#>
[CmdletBinding()]
param(
    [string]$PagesRepo = 'D:\vijay\Documents\whywatt',
    [switch]$Push
)

$ErrorActionPreference = 'Stop'

$Src     = Join-Path (Split-Path $PSScriptRoot -Parent) 'docs\explainer'
$DestRel = 'explainer'
$Dest    = Join-Path $PagesRepo $DestRel

# --- sanity checks ---------------------------------------------------------
if (-not (Test-Path (Join-Path $Src 'index.html'))) {
    throw "Explainer not found at $Src"
}
if (-not (Test-Path (Join-Path $PagesRepo '.git'))) {
    throw "Pages repo not found at $PagesRepo (expected a git clone of vijaybala-git.github.io)"
}

Write-Host "Source : $Src"  -ForegroundColor Cyan
Write-Host "Target : $Dest" -ForegroundColor Cyan
Write-Host ""

# --- pull latest so we don't push onto a stale base ------------------------
# (skipped when the repo has no remote, e.g. a local test clone)
if (git -C $PagesRepo remote) {
    Write-Host "Pulling latest Pages repo..." -ForegroundColor Cyan
    git -C $PagesRepo pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
}

# --- mirror the explainer folder -------------------------------------------
# /MIR makes the destination an exact copy of the source (adds + deletes).
# It only touches <PagesRepo>\explainer, never sibling files.
Write-Host "Mirroring explainer..." -ForegroundColor Cyan
robocopy $Src $Dest /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
$rc = $LASTEXITCODE
# robocopy: 0-7 = success, 8+ = failure
if ($rc -ge 8) { throw "robocopy failed with exit code $rc" }

# --- stage + show what changed ---------------------------------------------
git -C $PagesRepo add -- $DestRel
$status = git -C $PagesRepo status --porcelain -- $DestRel

if (-not $status) {
    Write-Host "No changes to publish -- Pages repo already up to date." -ForegroundColor Green
    return
}

Write-Host ""
Write-Host "Pending changes:" -ForegroundColor Yellow
git -C $PagesRepo status --short -- $DestRel
Write-Host ""

if (-not $Push) {
    Write-Host "Dry run complete. Re-run with -Push to commit and publish." -ForegroundColor Yellow
    return
}

# --- commit + push ---------------------------------------------------------
$src_sha = git -C (Split-Path $PSScriptRoot -Parent) rev-parse --short HEAD
$stamp   = Get-Date -Format 'yyyy-MM-dd HH:mm'
git -C $PagesRepo commit -m "Publish WhyWatt? HEX explainer ($stamp, hes@$src_sha)"
if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

git -C $PagesRepo push origin main
if ($LASTEXITCODE -ne 0) { throw "git push failed" }

Write-Host ""
Write-Host "Published. Live in ~1 min at:" -ForegroundColor Green
Write-Host "  https://www.whywatt.org/explainer/"                 -ForegroundColor Green
Write-Host "  https://vijaybala-git.github.io/explainer/"          -ForegroundColor Green
