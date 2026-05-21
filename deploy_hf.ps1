# deploy_hf.ps1
# Deploys WhyWatt to Hugging Face, stripping binary files from history.
# Run from repo root: .\deploy_hf.ps1

$ErrorActionPreference = "Stop"

Write-Host "Creating HF deploy branch..." -ForegroundColor Cyan
git checkout -b hf-deploy

Write-Host "Stripping binary files from history..." -ForegroundColor Cyan

python -m git_filter_repo --path "docs/WhyWatt_Phase2_Spec.docx" --invert-paths --force
python -m git_filter_repo --path "docs/HES_Phase2_Spec.docx" --invert-paths --force
python -m git_filter_repo --path "docs/HES_Prototype_Feedback.docx" --invert-paths --force
python -m git_filter_repo --path "docs/echorixzontalimage.pdf" --invert-paths --force
python -m git_filter_repo --path "docs/assets/echo_logo.png" --invert-paths --force

Write-Host "Pushing to Hugging Face..." -ForegroundColor Cyan
git push hf-whywatt hf-deploy:main --force

Write-Host "Cleaning up..." -ForegroundColor Cyan
git checkout main --force
git branch -D hf-deploy

Write-Host "Done. HF deploy complete." -ForegroundColor Green
