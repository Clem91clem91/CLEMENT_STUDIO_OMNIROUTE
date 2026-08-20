$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$Artifacts = Join-Path $Repo "artifacts"
$Report = Join-Path $Artifacts "OMNIROUTE_CERTIFICATION.md"

Write-Host "============================================================"
Write-Host "CLEMENT - P0-03 OMNIROUTE SHADOW CERTIFICATION"
Write-Host "============================================================"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "VENV_PYTHON_NOT_FOUND=$Python"
}

New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null

Push-Location $Repo
try {
    $Status = @(& git status --porcelain)
    if ($Status.Count -gt 0) {
        throw "WORKTREE_NOT_CLEAN"
    }

    $Branch = (& git branch --show-current).Trim()
    $Head = (& git rev-parse HEAD).Trim()
    Write-Host "BRANCH=$Branch"
    Write-Host "HEAD=$Head"

    & $Python -m compileall -q src tests scripts
    if ($LASTEXITCODE -ne 0) { throw "COMPILE_FAILED" }
    Write-Host "COMPILE=PASS"

    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "PYTEST_FAILED" }
    Write-Host "PYTEST=PASS"

    & $Python scripts\certify_shadow.py --report $Report
    if ($LASTEXITCODE -ne 0) { throw "LIVE_CERTIFICATION_FAILED" }

    Write-Host "LIVE_CERTIFICATION=PASS_OR_PARTIAL"
    Write-Host "REPORT=$Report"

    $AfterStatus = @(& git status --porcelain)
    if ($AfterStatus.Count -eq 0) {
        Write-Host "WORKTREE_AFTER=CLEAN"
    }
    else {
        Write-Host "WORKTREE_AFTER=DIRTY"
    }

    Write-Host "MERGE_EXECUTED=NO"
    Write-Host "TAG_CREATED=NO"
    Write-Host "RELEASE_CREATED=NO"
}
finally {
    Pop-Location
}
