# deploy_fly.ps1
# Deploys WhyWatt to Fly.io.
# Requires: flyctl installed and authenticated (fly auth login)
# Run from repo root: .\deploy_fly.ps1

Write-Host "Deploying WhyWatt to Fly.io..." -ForegroundColor Cyan

fly deploy
$result = $LASTEXITCODE

if ($result -ne 0) {
    Write-Host "Fly deploy FAILED. Check error above." -ForegroundColor Red
    exit 1
}

Write-Host "Done. WhyWatt is live on Fly.io." -ForegroundColor Green
Write-Host "App URL: https://whywatt.fly.dev" -ForegroundColor Cyan
Write-Host "Logs:    fly logs" -ForegroundColor Gray
Write-Host "Status:  fly status" -ForegroundColor Gray
