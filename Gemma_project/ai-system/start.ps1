# Medical AI System - Start Script
# Run from project root: cd D:\Ripha_projects\Gemma_project\medical-ai-system && .\start.ps1

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $base
$venvPython = "$base\.venv\Scripts\python.exe"
$venvPip    = "$base\.venv\Scripts\pip.exe"

# Ensure Docker and Ollama are in PATH
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) { $env:PATH = "$dockerBin;$env:PATH" }
$ollamaBin = "$env:LOCALAPPDATA\Programs\Ollama"
if (Test-Path $ollamaBin) { $env:PATH = "$ollamaBin;$env:PATH" }

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Medical AI System - Starting Services" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Ensure Ollama is running ────────────────────────────────────────────
Write-Host "[1] Checking Ollama..." -ForegroundColor Yellow
$ollamaRunning = $false
try {
    $null = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 4
    $ollamaRunning = $true
    Write-Host "    Ollama is running." -ForegroundColor Green
} catch {
    Write-Host "    Starting Ollama..." -ForegroundColor Gray
    $ollamaExe = if (Get-Command ollama -ErrorAction SilentlyContinue) { "ollama" } else { "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
    Start-Process $ollamaExe -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep -Seconds 6
    try {
        $null = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 5
        Write-Host "    Ollama started." -ForegroundColor Green
    } catch {
        Write-Host "    WARNING: Ollama not responding. Install it first with setup.ps1" -ForegroundColor Red
    }
}

# ── 2. Start Docker services (Postgres + Qdrant) ───────────────────────────
Write-Host ""
Write-Host "[2] Starting Docker services (PostgreSQL + Qdrant)..." -ForegroundColor Yellow
$dockerOk = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
if ($dockerOk) {
    try {
        & docker info 2>$null | Out-Null
        Write-Host "    Docker is running. Starting containers..." -ForegroundColor Gray
        & docker compose up -d postgres qdrant
        Write-Host "    Waiting for services to be healthy..." -ForegroundColor Gray
        Start-Sleep -Seconds 10

        # Check postgres
        $pgReady = $false
        for ($i = 0; $i -lt 12; $i++) {
            $check = & docker exec medical_postgres pg_isready -U admin -d medical_ai 2>&1
            if ($check -match "accepting connections") {
                $pgReady = $true; break
            }
            Start-Sleep -Seconds 3
        }
        if ($pgReady) {
            Write-Host "    PostgreSQL ready." -ForegroundColor Green
        } else {
            Write-Host "    WARNING: PostgreSQL may not be ready yet." -ForegroundColor Yellow
        }
        Write-Host "    Qdrant started on port 6333." -ForegroundColor Green
    } catch {
        Write-Host "    Docker is installed but not running. Please start Docker Desktop first." -ForegroundColor Red
        Write-Host "    Continuing without Docker (backend will use fallback modes)..." -ForegroundColor Yellow
    }
} else {
    Write-Host "    Docker not found. Run setup.ps1 first." -ForegroundColor Red
    Write-Host "    Backend will start without DB (limited functionality)." -ForegroundColor Yellow
}

# ── 3. Start FastAPI backend ───────────────────────────────────────────────
Write-Host ""
Write-Host "[3] Starting FastAPI backend on port 8000..." -ForegroundColor Yellow
if (-not (Test-Path $venvPython)) {
    Write-Host "    .venv not found. Run setup.ps1 first." -ForegroundColor Red
    $venvPython = "python"
}

$backendJob = Start-Process -FilePath $venvPython -ArgumentList `
    "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" `
    -WorkingDirectory $base `
    -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 5
try {
    $null = Invoke-RestMethod "http://localhost:8000/api/health" -TimeoutSec 5
    Write-Host "    Backend running at http://localhost:8000" -ForegroundColor Green
    Write-Host "    API docs at http://localhost:8000/docs" -ForegroundColor Gray
} catch {
    Write-Host "    Backend starting (may take a moment)..." -ForegroundColor Gray
}

# ── 4. Start React frontend ────────────────────────────────────────────────
Write-Host ""
Write-Host "[4] Starting React frontend on port 3000..." -ForegroundColor Yellow

# Resolve npm.cmd explicitly — Start-Process won't pick up .cmd via PATHEXT
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npmCmd) {
    $npmCmd = (Get-Command npm -ErrorAction SilentlyContinue).Source
}

if (-not $npmCmd) {
    Write-Host "    ERROR: npm not found in PATH. Install Node.js from https://nodejs.org" -ForegroundColor Red
} else {
    # Use cmd.exe wrapper so PowerShell launches the .cmd shim correctly
    $frontendProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm", "run", "dev" `
        -WorkingDirectory "$base\frontend" `
        -PassThru -WindowStyle Minimized
    Write-Host "    Frontend starting at http://localhost:3000 (PID $($frontendProc.Id))" -ForegroundColor Green
}

Start-Sleep -Seconds 4

# ── 5. Ingest RAG data ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "[5] Ingesting RAG knowledge base..." -ForegroundColor Yellow
try {
    & $venvPython -c @"
import sys, os
sys.path.insert(0, r'$base')
os.chdir(r'$base')
from backend.rag.embeddings import load_and_ingest_all
load_and_ingest_all('data/medical')
"@
    Write-Host "    RAG data ingested." -ForegroundColor Green
} catch {
    Write-Host "    RAG ingestion skipped (Qdrant may not be ready yet). Run manually later." -ForegroundColor Yellow
}

# ── Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  All services started!" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  Ollama:    http://localhost:11434" -ForegroundColor Cyan
Write-Host "  Qdrant:    http://localhost:6333" -ForegroundColor Cyan
Write-Host "  Postgres:  localhost:5432" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop monitoring." -ForegroundColor Gray
Write-Host "  Backend and frontend run in background." -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Open browser
Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"
