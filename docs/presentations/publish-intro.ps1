<#
.SYNOPSIS
  Publish the intro_whywatt_v1 deck to the GitHub Pages repo (www.whywatt.org).

.DESCRIPTION
  Mirrors docs/presentations/intro_whywatt_v1 into <PagesRepo>/presentations/intro_whywatt_v1,
  then commits and pushes the Pages repo. Existing files in the Pages repo (index.html, etc.)
  are left untouched -- only the presentations/intro_whywatt_v1 subfolder is mirrored.

.PARAMETER PagesRepo
  Path to the local clone of vijaybala-git.github.io. Default: D:\vijay\Documents\whywatt

.PARAMETER Push
  Actually push to origin/main. Without this flag the script does a dry run
  (mirror + show git status) and does NOT commit or push.

.EXAMPLE
  # Preview what would change, no push:
  powershell -ExecutionPolicy Bypass -File docs\presentations\publish-intro.ps1

  # Mirror, commit, and push live:
  powershell -ExecutionPolicy Bypass -File docs\presentations\publish-intro.ps1 -Push
#>
[CmdletBinding()]
param(
    [string]$PagesRepo = 'D:\vijay\Documents\whywatt',
    [switch]$Push
)

$ErrorActionPreference = 'Stop'

$SrcName = 'intro_whywatt_v1'
$Src     = Join-Path $PSScriptRoot $SrcName
$DestRel = "presentations\$SrcName"
$Dest    = Join-Path $PagesRepo $DestRel

# --- sanity checks ---------------------------------------------------------
if (-not (Test-Path (Join-Path $Src 'index.html'))) {
    throw "Source deck not found at $Src"
}
if (-not (Test-Path (Join-Path $PagesRepo '.git'))) {
    throw "Pages repo not found at $PagesRepo (expected a git clone of vijaybala-git.github.io)"
}

Write-Host "Source : $Src"  -ForegroundColor Cyan
Write-Host "Target : $Dest" -ForegroundColor Cyan
Write-Host ""

# --- pull latest so we don't push onto a stale base ------------------------
Write-Host "Pulling latest Pages repo..." -ForegroundColor Cyan
git -C $PagesRepo pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

# --- mirror the deck folder ------------------------------------------------
# /MIR makes the destination an exact copy of the source (adds + deletes).
# It only touches presentations\intro_whywatt_v1, never sibling files.
Write-Host "Mirroring deck..." -ForegroundColor Cyan
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
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
git -C $PagesRepo commit -m "Publish intro_whywatt_v1 deck ($stamp)"
if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

git -C $PagesRepo push origin main
if ($LASTEXITCODE -ne 0) { throw "git push failed" }

Write-Host ""
Write-Host "Published. Live in ~1 min at:" -ForegroundColor Green
Write-Host "  https://www.whywatt.org/presentations/$SrcName/"         -ForegroundColor Green
Write-Host "  https://vijaybala-git.github.io/presentations/$SrcName/" -ForegroundColor Green
