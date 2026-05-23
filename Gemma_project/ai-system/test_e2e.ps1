# Medical AI System - End-to-End Test Script
# Run after start.ps1: .\test_e2e.ps1

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = "$base\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { $venvPython = "python" }

# Ensure Docker and Ollama are in PATH
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) { $env:PATH = "$dockerBin;$env:PATH" }

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Medical AI System - E2E Test" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$pass = 0; $fail = 0

function Check($label, $ok) {
    if ($ok) {
        Write-Host "  [PASS] $label" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  [FAIL] $label" -ForegroundColor Red
        $script:fail++
    }
}

# 1. Backend health
Write-Host "[1] Backend health check..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod "http://localhost:8000/api/health" -TimeoutSec 5
    Check "Backend is running" ($health.status -eq "ok")
    Check "Ollama connected" ($health.ollama.status -eq "ok")
} catch {
    Check "Backend is running" $false
    Check "Ollama connected" $false
}

# 2. Docker services
Write-Host ""
Write-Host "[2] Docker services..." -ForegroundColor Yellow
try {
    $pgCheck = & docker exec medical_postgres pg_isready -U admin -d medical_ai 2>&1
    Check "PostgreSQL healthy" ($pgCheck -match "accepting")
} catch {
    Check "PostgreSQL healthy" $false
}
try {
    $qdrantCheck = Invoke-RestMethod "http://localhost:6333/healthz" -TimeoutSec 3
    Check "Qdrant healthy" $true
} catch {
    Check "Qdrant healthy" $false
}

# 3. Doctors endpoint
Write-Host ""
Write-Host "[3] API endpoints..." -ForegroundColor Yellow
try {
    $doctors = Invoke-RestMethod "http://localhost:8000/api/doctors" -TimeoutSec 10
    Check "GET /api/doctors returns data" ($doctors.Count -gt 0)
    Write-Host "      Found $($doctors.Count) doctors: $($doctors | ForEach-Object { $_.name } | Join-String ', ')" -ForegroundColor Gray
} catch {
    Check "GET /api/doctors returns data" $false
}

# 4. Submit patient request (the main test)
Write-Host ""
Write-Host "[4] Patient request workflow..." -ForegroundColor Yellow
$workflowId = $null
try {
    $body = '{"text": "I need to book an appointment with a cardiologist, my name is John Smith", "patient_name": "John Smith"}'
    $response = Invoke-RestMethod "http://localhost:8000/api/patient/request" `
        -Method POST -Body $body -ContentType "application/json" -TimeoutSec 15
    $workflowId = $response.workflow_id
    Check "POST /api/patient/request succeeds" ($null -ne $workflowId)
    Write-Host "      Workflow ID: $workflowId" -ForegroundColor Gray
    Write-Host "      Intent: $($response.intent | ConvertTo-Json -Compress)" -ForegroundColor Gray
} catch {
    Check "POST /api/patient/request succeeds" $false
}

# 5. Poll workflow status
if ($workflowId) {
    Write-Host ""
    Write-Host "[5] Watching workflow execute..." -ForegroundColor Yellow
    $maxWait = 120  # seconds
    $elapsed = 0
    $finalStatus = $null
    $slots = @()

    while ($elapsed -lt $maxWait) {
        Start-Sleep -Seconds 3
        $elapsed += 3
        try {
            $wf = Invoke-RestMethod "http://localhost:8000/api/workflow/$workflowId" -TimeoutSec 5
            $completedSteps = @($wf.step_results.PSObject.Properties.Name)
            Write-Host "      [$elapsed s] Status: $($wf.status) | Steps done: $($completedSteps -join ', ')" -ForegroundColor Gray

            if ($wf.available_slots.Count -gt 0) { $slots = $wf.available_slots }

            if ($wf.status -in @("completed", "error", "awaiting_input")) {
                $finalStatus = $wf.status
                break
            }
        } catch { }
    }

    Check "Workflow completed or awaiting input" ($finalStatus -in @("completed", "awaiting_input"))
    Check "verify_patient step ran" ($null -ne $wf.step_results.verify_patient)
    Check "find_slots step ran" ($null -ne $wf.step_results.find_slots)

    # 6. Confirm a slot if available
    if ($slots.Count -gt 0) {
        Write-Host ""
        Write-Host "[6] Confirming first available slot..." -ForegroundColor Yellow
        $slot = $slots[0]
        Write-Host "      Slot: Dr. $($slot.doctor_name) on $($slot.date) at $($slot.time)" -ForegroundColor Gray
        try {
            $confirmBody = $slot | ConvertTo-Json
            $confirmResp = Invoke-RestMethod "http://localhost:8000/api/workflow/$workflowId/confirm" `
                -Method POST -Body $confirmBody -ContentType "application/json" -TimeoutSec 10
            Check "POST /api/workflow/confirm accepted" ($confirmResp.status -ne $null)

            # Wait for completion
            Start-Sleep -Seconds 8
            $finalWf = Invoke-RestMethod "http://localhost:8000/api/workflow/$workflowId" -TimeoutSec 5
            Check "Workflow completed after confirmation" ($finalWf.status -eq "completed")

            if ($finalWf.booking) {
                $bk = $finalWf.booking
                Check "Appointment created" ($null -ne $bk.appointment_id -or $null -ne $bk.slot_id)
                Write-Host "      Booking: $($bk | ConvertTo-Json -Compress)" -ForegroundColor Gray
            }
        } catch {
            Check "Slot confirmation" $false
        }
    } else {
        Write-Host "[6] Skipped slot confirmation (no slots returned)." -ForegroundColor Gray
    }

    # 7. Check DB for appointment
    Write-Host ""
    Write-Host "[7] Verifying database record..." -ForegroundColor Yellow
    try {
        $dbCheck = & docker exec medical_postgres psql -U admin -d medical_ai `
            -c "SELECT id, status, workflow_id FROM appointments WHERE workflow_id='$workflowId' LIMIT 1;" 2>&1
        Check "Appointment written to PostgreSQL" ($dbCheck -match $workflowId)
        Write-Host "      $dbCheck" -ForegroundColor Gray
    } catch {
        Write-Host "      DB check skipped (Docker unavailable)" -ForegroundColor Gray
    }

    # 8. Check notification log
    Write-Host ""
    Write-Host "[8] Checking notification log..." -ForegroundColor Yellow
    try {
        $notifyCheck = & docker exec medical_postgres psql -U admin -d medical_ai `
            -c "SELECT id, type, recipient FROM notifications WHERE workflow_id='$workflowId' LIMIT 3;" 2>&1
        Check "Notification logged" ($notifyCheck -notmatch "0 rows")
        Write-Host "      $notifyCheck" -ForegroundColor Gray
    } catch {
        Write-Host "      Notification DB check skipped" -ForegroundColor Gray
    }
}

# Summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  E2E Test Summary" -ForegroundColor Cyan
Write-Host "  PASSED: $pass  FAILED: $fail" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
if ($fail -gt 0) {
    Write-Host "  Some checks failed. Common fixes:" -ForegroundColor Yellow
    Write-Host "  - Run setup.ps1 if first time" -ForegroundColor Gray
    Write-Host "  - Ensure Docker Desktop is running" -ForegroundColor Gray
    Write-Host "  - Wait longer for Ollama to load models" -ForegroundColor Gray
    Write-Host "  - Check backend logs in its terminal window" -ForegroundColor Gray
}
