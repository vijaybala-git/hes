# deploy_hf.ps1
# Deploys WhyWatt to a Hugging Face Space, with confirmation gates.
#
# Two targets (pick with -Target):
#   prototype  -> remote 'hf'         -> vijaybala-hug/hes-prototype   (BLEEDING EDGE; Phase 6+)
#   default    -> remote 'hf-whywatt' -> vijaybala-hug/whywatt         (STABLE; users; stays Phase 5)
#
# Run from repo root:
#   .\deploy_hf.ps1                          deploy 'main' to the PROTOTYPE space (default)
#   .\deploy_hf.ps1 -Target prototype        same, explicit
#   .\deploy_hf.ps1 -Target default          deploy to the STABLE space (extra confirmation!)
#   .\deploy_hf.ps1 -Branch phase5           deploy a specific branch/tag/commit
#   .\deploy_hf.ps1 -Remote hf               advanced: override the remote name directly
#   .\deploy_hf.ps1 -Yes                     skip the plain yes/no prompt (PROTOTYPE only;
#                                            the STABLE type-the-name gate is never skippable)
#
# HF builds the Space from the Dockerfile, which copies src/, data/, docs/assets/ and public/
# into the image. Only those paths affect the running Space.
#
# Some repo paths are NOT part of the running Space and must not be uploaded to HF:
#   - docs/presentations/  - slide decks + images (not served)
#   - data/climate/sources/ and data/rates/sources/ - raw TMYx weather .zip and EIA .xlsx
#     snapshots (build-time inputs to scripts/build_*.py only; the app reads the processed JSON).
#     HF's hub rejects large non-LFS blobs, so they must be stripped.
# The script strips $ExcludePaths from history in a throwaway clone, then force-pushes that
# cleaned history to the Space's main branch. Your local repo (and GitHub) are never rewritten.

param(
    [ValidateSet("prototype", "default")]
    [string]   $Target       = "prototype",
    [string]   $Branch       = "main",
    [string]   $Remote       = "",          # optional override; derived from -Target when empty
    [switch]   $Yes,                          # skip the plain confirm (prototype only)
    [string[]] $ExcludePaths = @(
        "docs/presentations",
        "data/climate/sources",
        "data/rates/sources",
        # Legacy binary that HF (Git-Xet/LFS) rejects; superseded by rate_projection_curves.svg.
        # It only ever existed in Phase 6 history, so strip it from every deployed commit.
        "public/help/rate_projection_curves.png"
    )
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path

# --- Target -> remote mapping ----------------------------------------------
$targetMap = @{
    prototype = @{ Remote = "hf";         Label = "PROTOTYPE  (bleeding edge)"; Stable = $false }
    default   = @{ Remote = "hf-whywatt"; Label = "DEFAULT / STABLE  (live users)"; Stable = $true }
}
if ([string]::IsNullOrWhiteSpace($Remote)) { $Remote = $targetMap[$Target].Remote }
$isStable    = $targetMap[$Target].Stable
$targetLabel = $targetMap[$Target].Label

# --- Safety checks ----------------------------------------------------------
if (-not (Test-Path ".git")) {
    throw "Run this from the repo root (no .git directory found here)."
}

git remote get-url $Remote *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Remote '$Remote' not found. Add it with: git remote add $Remote <space-url>"
}

git rev-parse --verify $Branch *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Branch '$Branch' not found. Merge your changes into '$Branch' first, or pass -Branch."
}

$spaceUrl  = (git remote get-url $Remote).Trim()
$spaceName = (($spaceUrl -replace '/$', '') -split '/' | Select-Object -Last 1)
$commit    = (git log -1 --format="%h  %s" $Branch).Trim()

# --- Confirmation gate ------------------------------------------------------
Write-Host ""
Write-Host "================ HF DEPLOY - CONFIRM ================" -ForegroundColor Cyan
Write-Host ("  Target :  {0}" -f $targetLabel)
Write-Host ("  Space  :  {0}" -f $spaceUrl)
Write-Host ("  Remote :  {0}" -f $Remote)
Write-Host ("  Branch :  {0}" -f $Branch)
Write-Host ("  Commit :  {0}" -f $commit)
Write-Host ("  Excl.  :  {0}" -f ($ExcludePaths -join ', ')) -ForegroundColor DarkGray
Write-Host "  Action :  FORCE-PUSH cleaned history -> the Space's 'main' (replaces it)" -ForegroundColor Yellow

# Warn about uncommitted changes - only committed $Branch is deployed.
$dirty = (git status --porcelain)
if (-not [string]::IsNullOrWhiteSpace($dirty)) {
    Write-Host "  NOTE   :  You have uncommitted changes; they will NOT be deployed" -ForegroundColor Yellow
    Write-Host "            (only the committed tip of '$Branch' is pushed)." -ForegroundColor Yellow
}
Write-Host "====================================================" -ForegroundColor Cyan

if ($isStable) {
    # Stronger gate for the live/stable Space: it is meant to stay on Phase 5, so deploying to
    # it must be deliberate. This gate is NEVER skipped by -Yes.
    Write-Host ""
    Write-Host "!! This is the STABLE Space that live users depend on (currently Phase 5)." -ForegroundColor Red
    Write-Host "!! Deploying here changes what everyone sees. Do NOT push bleeding-edge work here." -ForegroundColor Red
    $typed = Read-Host "   To proceed, type the Space name exactly ('$spaceName')"
    if ($typed -ne $spaceName) {
        Write-Host "Aborted - name did not match ('$typed' != '$spaceName')." -ForegroundColor Yellow
        return
    }
}

if (-not $Yes) {
    $ans = Read-Host "Proceed with deploy? Type 'yes' to continue"
    if ($ans -ne "yes") {
        Write-Host "Aborted." -ForegroundColor Yellow
        return
    }
} elseif (-not $isStable) {
    Write-Host "(-Yes) Skipping plain confirmation for the prototype space." -ForegroundColor DarkGray
}

# --- Resolve a git-filter-repo invocation ----------------------------------
# Tries, in order: the `git filter-repo` subcommand, the repo venv's python,
# then a system python. Returns a hashtable @{ Exe; Pre }.
function Get-FilterRepo {
    $venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $tries = @(
        @{ Exe = "git";    Pre = @("filter-repo") },
        @{ Exe = $venvPy;  Pre = @("-m", "git_filter_repo") },
        @{ Exe = "python"; Pre = @("-m", "git_filter_repo") }
    )
    foreach ($t in $tries) {
        if ($t.Exe -ne "git" -and $t.Exe -ne "python" -and -not (Test-Path $t.Exe)) { continue }
        try {
            & $t.Exe @($t.Pre + @("--version")) *> $null
            if ($LASTEXITCODE -eq 0) { return $t }
        } catch { }
    }
    throw "git-filter-repo not found. Install it with:  pip install git-filter-repo"
}

# --- Force-remove a directory tree (handles read-only .git pack files) ------
function Remove-TreeForce([string]$path) {
    if (-not (Test-Path $path)) { return }
    try {
        Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue |
            ForEach-Object { try { $_.Attributes = 'Normal' } catch { } }
    } catch { }
    Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
}

# --- Deploy in a throwaway clone -------------------------------------------
$fr  = Get-FilterRepo
$tmp = Join-Path $env:TEMP ("whywatt-hf-deploy-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))

Write-Host ""
Write-Host "Deploying '$Branch' to '$Remote' (-> main) ..." -ForegroundColor Cyan
Write-Host "  Space:    $spaceUrl"                          -ForegroundColor DarkGray
Write-Host "  Workdir:  $tmp"                               -ForegroundColor DarkGray

try {
    git clone --quiet --branch $Branch --single-branch "$RepoRoot" "$tmp"
    if ($LASTEXITCODE -ne 0) { throw "Failed to clone '$Branch' into the temp workdir." }

    # Strip the excluded paths from the clone's history.
    $frArgs = @()
    foreach ($p in $ExcludePaths) { $frArgs += @("--path", $p) }
    $frArgs += @("--invert-paths", "--force")

    Push-Location $tmp
    try {
        & $fr.Exe @($fr.Pre + $frArgs)
        if ($LASTEXITCODE -ne 0) { throw "git-filter-repo failed while stripping excluded paths." }

        # filter-repo drops remotes; re-add the Space and push the cleaned history.
        # --force because the Space's main is a deploy target, not a shared history.
        git remote add hf_target "$spaceUrl"
        git push hf_target "HEAD:main" --force
        if ($LASTEXITCODE -ne 0) { throw "Push to the Space failed." }
    }
    finally {
        Pop-Location
    }

    Write-Host "Done. HF deploy complete -> $targetLabel" -ForegroundColor Green
    Write-Host "Watch the build under the 'Logs' tab: $spaceUrl" -ForegroundColor DarkGray
}
finally {
    Remove-TreeForce $tmp
}
