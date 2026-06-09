# deploy_hf.ps1
# Deploys WhyWatt to Hugging Face, stripping binary/archive files from history.
# Run from repo root: .\deploy_hf.ps1

$ErrorActionPreference = "Stop"

Write-Host "Creating HF deploy branch..." -ForegroundColor Cyan
git checkout -b hf-deploy

Write-Host "Stripping binary/archive files from history..." -ForegroundColor Cyan

# Design archive — no runtime value on HF
python -m git_filter_repo --path "docs/HES-design.zip" --invert-paths --force

Write-Host "Pushing to Hugging Face..." -ForegroundColor Cyan
git push hf-whywatt hf-deploy:main --force

Write-Host "Cleaning up..." -ForegroundColor Cyan
git checkout main --force
git branch -D hf-deploy

Write-Host "Done. HF deploy complete." -ForegroundColor Green
