# deploy_hf.ps1
# Deploys WhyWatt to the Hugging Face Space via the `hf-whywatt` remote.
# Run from repo root:  .\deploy_hf.ps1            (deploys main)
#                      .\deploy_hf.ps1 -Branch x  (deploys branch x)
#
# HF builds the Space from the Dockerfile, which copies src/, data/,
# docs/assets/ and public/ into the image. Only those paths affect the
# running Space; everything else in the repo is just along for the ride,
# so there is no need to rewrite history before pushing.

param(
    [string]$Branch = "main",
    [string]$Remote = "hf-whywatt"
)

$ErrorActionPreference = "Stop"

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

$spaceUrl = git remote get-url $Remote
Write-Host "Deploying '$Branch' to $Remote (-> main) ..." -ForegroundColor Cyan
Write-Host "  Space: $spaceUrl" -ForegroundColor DarkGray

# Push the chosen branch straight to the Space's main branch.
# --force because the Space's main is a deploy target, not a shared history.
git push $Remote "${Branch}:main" --force

Write-Host "Done. HF deploy complete." -ForegroundColor Green
Write-Host "Watch the build under the 'Logs' tab on the Space page." -ForegroundColor DarkGray

# --- Note on stripping large/binary files -----------------------------------
# The previous version ran `git filter-repo` to strip docs/HES-design.zip from
# history. That file is no longer tracked, and filter-repo rewrites EVERY local
# ref (including main), which would diverge your local repo from GitHub.
# If you ever need to keep a large binary out of the pushed history, do it in a
# throwaway clone so the working repo is never rewritten, e.g.:
#
#   git clone . ../whywatt-hf-tmp
#   cd ../whywatt-hf-tmp
#   python -m git_filter_repo --path <big/file> --invert-paths --force
#   git remote add hf <space-url>
#   git push hf HEAD:main --force
#   cd ..; Remove-Item -Recurse -Force ../whywatt-hf-tmp
