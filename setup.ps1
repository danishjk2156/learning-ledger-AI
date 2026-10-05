# Learning Ledger - Quick Setup Script for Windows PowerShell
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Setting up Learning Ledger..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Sync dependencies with uv if available, or notify user
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "[1/4] Installing Python dependencies with uv..." -ForegroundColor Yellow
    uv sync
} else {
    Write-Host "[1/4] 'uv' not found. Installing dependencies via pip..." -ForegroundColor Yellow
    python -m pip install -e .
}

# 2. Clone Retraction Watch dataset for offline retraction checking
if (-not (Test-Path "retraction-watch-data")) {
    Write-Host "[2/4] Cloning Retraction Watch dataset (offline cache)..." -ForegroundColor Yellow
    git clone https://gitlab.com/crossref/retraction-watch-data 2>$null
} else {
    Write-Host "[2/4] Retraction Watch dataset already present." -ForegroundColor Green
}

# 3. Create necessary local directories
Write-Host "[3/4] Ensuring local directories exist..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path ".ledger", "library", "tests" | Out-Null

# 4. Create .env from template if missing
if (-not (Test-Path ".env")) {
    Write-Host "[4/4] Creating .env from template (.env.example)..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "Created .env - please edit it to add your API keys!" -ForegroundColor Magenta
} else {
    Write-Host "[4/4] .env already exists." -ForegroundColor Green
}

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Add your GOOGLE_API_KEY and OPENROUTER_API_KEY into .env"
Write-Host "  2. Launch Web UI: uv run python -m src.web (or CLI: uv run python -m src.main)"
