# Medical AI System - One-time Setup Script
# Run as Administrator: Right-click PowerShell -> Run as Administrator
# Then: cd D:\Ripha_projects\Gemma_project\medical-ai-system && .\setup.ps1

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $base

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Local AI Platform - Setup" -ForegroundColor Cyan
Write-Host "  CPU-only mode (Intel Core Ultra 7 155U)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Install Ollama
Write-Host "[1/6] Checking Ollama..." -ForegroundColor Yellow
$ollamaInstalled = $null -ne (Get-Command ollama -ErrorAction SilentlyContinue)
if (-not $ollamaInstalled) {
    Write-Host "      Installing Ollama via winget..." -ForegroundColor Gray
    winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
    Write-Host "      Ollama installed. Starting service..." -ForegroundColor Green
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep -Seconds 5
} else {
    Write-Host "      Ollama already installed." -ForegroundColor Green
    try {
        $null = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3
        Write-Host "      Ollama service is running." -ForegroundColor Green
    } catch {
        Write-Host "      Starting Ollama service..." -ForegroundColor Gray
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Minimized
        Start-Sleep -Seconds 5
    }
}

# Step 2: Pull models (CPU-only)
Write-Host ""
Write-Host "[2/6] Pulling AI models (CPU-only mode)..." -ForegroundColor Yellow
Write-Host "      This will take 5-20 minutes on first run." -ForegroundColor Gray
Write-Host ""

$models = @("gemma3:4b", "phi4-mini", "nomic-embed-text")
foreach ($model in $models) {
    Write-Host "      Pulling $model ..." -ForegroundColor Gray
    & ollama pull $model
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      WARNING: Failed to pull $model. Will retry at runtime." -ForegroundColor Yellow
    } else {
        Write-Host "      $model ready." -ForegroundColor Green
    }
}

# Step 3: Install Docker Desktop
Write-Host ""
Write-Host "[3/6] Checking Docker..." -ForegroundColor Yellow
$dockerInstalled = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
if (-not $dockerInstalled) {
    Write-Host "      Installing Docker Desktop via winget..." -ForegroundColor Gray
    Write-Host "      NOTE: Docker Desktop requires a restart. After restart, re-run start.ps1" -ForegroundColor Yellow
    winget install Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
    Write-Host ""
    Write-Host "  *** Docker Desktop installed. Please RESTART your computer, then run start.ps1 ***" -ForegroundColor Magenta
    Write-Host ""
} else {
    Write-Host "      Docker already installed." -ForegroundColor Green
    try {
        & docker info 2>$null | Out-Null
        Write-Host "      Docker is running." -ForegroundColor Green
    } catch {
        Write-Host "      Starting Docker Desktop..." -ForegroundColor Gray
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        Write-Host "      Waiting 30s for Docker to start..." -ForegroundColor Gray
        Start-Sleep -Seconds 30
    }
}

# Step 4: Install Python packages
Write-Host ""
Write-Host "[4/6] Installing Python packages..." -ForegroundColor Yellow
Write-Host "      Using Python 3.11 compatible packages..." -ForegroundColor Gray

$venvPath = "$base\.venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "      Creating virtual environment..." -ForegroundColor Gray
    python -m venv $venvPath
}

$pip = "$venvPath\Scripts\pip.exe"
& $pip install --upgrade pip --quiet
& $pip install -r "$base\backend\requirements.txt"
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Python packages installed." -ForegroundColor Green
} else {
    Write-Host "      Some packages failed. Check output above." -ForegroundColor Yellow
}

# Step 5: Install Node packages
Write-Host ""
Write-Host "[5/6] Installing Node.js packages for frontend..." -ForegroundColor Yellow
Set-Location "$base\frontend"
& npm install
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Node packages installed." -ForegroundColor Green
} else {
    Write-Host "      npm install failed. Check output above." -ForegroundColor Yellow
}
Set-Location $base

# Step 6: Install Tesseract OCR (for scanned PDFs)
Write-Host ""
Write-Host "[6/6] Checking Tesseract OCR..." -ForegroundColor Yellow
$tesseractInstalled = $null -ne (Get-Command tesseract -ErrorAction SilentlyContinue)
if (-not $tesseractInstalled) {
    Write-Host "      Installing Tesseract via winget..." -ForegroundColor Gray
    Write-Host "      (Used as OCR fallback when a PDF is scanned/image-based.)" -ForegroundColor Gray
    winget install UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
    if ($null -ne (Get-Command tesseract -ErrorAction SilentlyContinue)) {
        Write-Host "      Tesseract installed." -ForegroundColor Green
    } else {
        Write-Host "      Tesseract install couldn't be auto-verified - you may need to restart PowerShell." -ForegroundColor Yellow
        Write-Host "      If OCR is required, also set TESSERACT_CMD in .env to the full path of tesseract.exe." -ForegroundColor Yellow
    }
} else {
    Write-Host "      Tesseract already installed." -ForegroundColor Green
}

# Done
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  Next: Run .\start.ps1 to launch everything" -ForegroundColor Green
Write-Host "  Then visit:" -ForegroundColor Green
Write-Host "    React UI:     http://localhost:3000" -ForegroundColor Green
Write-Host "    OpenWebUI:    http://localhost:3001  (after docker compose up)" -ForegroundColor Green
Write-Host "    API docs:     http://localhost:8000/docs" -ForegroundColor Green
Write-Host "    OpenAI API:   http://localhost:8000/v1/chat/completions" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
