# deploy_hf.ps1
# Deploys WhyWatt to the Hugging Face Space.
# Run from repo root:  .\deploy_hf.ps1                 (deploys main)
#                      .\deploy_hf.ps1 -Branch x       (deploys branch x)
#                      .\deploy_hf.ps1 -Remote hf      (override remote name)
#
# HF builds the Space from the Dockerfile, which copies src/, data/,
# docs/assets/ and public/ into the image. Only those paths affect the
# running Space.
#
# Some repo paths are NOT part of the running Space and we do not want their
# blobs uploaded to HF:
#   - docs/presentations/  — slide decks + images (not served)
#   - data/climate/sources/ and data/rates/sources/ — raw TMYx weather .zip and
#     EIA .xlsx snapshots. They are build-time inputs to scripts/build_*.py only;
#     the app reads the processed JSON (tmy3_zones.json, eia_rates_by_utility.json),
#     never these. HF's hub rejects large non-LFS blobs, so they must be stripped.
# The script strips the paths in $ExcludePaths from history *in a throwaway
# clone*, then force-pushes that cleaned history to the Space's main branch.
# Your local repo (and GitHub) are never rewritten.

param(
    [string]   $Branch       = "main",
    [string]   $Remote       = "hf",
    [string[]] $ExcludePaths = @(
        "docs/presentations",
        "data/climate/sources",
        "data/rates/sources"
    )
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path

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

$spaceUrl = (git remote get-url $Remote).Trim()

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

Write-Host "Deploying '$Branch' to '$Remote' (-> main) ..." -ForegroundColor Cyan
Write-Host "  Space:    $spaceUrl"                          -ForegroundColor DarkGray
Write-Host "  Excluded: $($ExcludePaths -join ', ')"        -ForegroundColor DarkGray
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
        git remote add hf "$spaceUrl"
        git push hf "HEAD:main" --force
        if ($LASTEXITCODE -ne 0) { throw "Push to the Space failed." }
    }
    finally {
        Pop-Location
    }

    Write-Host "Done. HF deploy complete." -ForegroundColor Green
    Write-Host "Watch the build under the 'Logs' tab on the Space page." -ForegroundColor DarkGray
}
finally {
    Remove-TreeForce $tmp
}
