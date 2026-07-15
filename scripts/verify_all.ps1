param(
    [switch]$SkipE2E,
    [switch]$SkipCoverage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run uv sync --dev first."
}

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host "`n==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

Push-Location $root
try {
    Invoke-Checked "Database migrations" { & $python -m app.core.migrations }
    Invoke-Checked "Python compile check" { & $python -m compileall -q app agents routers services main.py models.py }
    Invoke-Checked "Backend lint" { & (Join-Path $root ".venv\Scripts\ruff.exe") check app tests }
    Invoke-Checked "Backend type check" { & (Join-Path $root ".venv\Scripts\mypy.exe") app }

    if ($SkipCoverage) {
        Invoke-Checked "Backend tests" { & $python -m pytest -q }
    }
    else {
        Invoke-Checked "Backend tests and core coverage" {
            & $python -m pytest `
                --cov=app.modules.courses.service `
                --cov=app.modules.materials.service `
                --cov=app.modules.learning.service `
                --cov=app.modules.agent.service `
                --cov=app.modules.agent.native_tool_agent `
                --cov=app.modules.agent.router `
                --cov=app.jobs.material_index_job `
                --cov-fail-under=70 `
                --cov-report=term-missing `
                -q
        }
    }

    Push-Location (Join-Path $root "frontend")
    try {
        Invoke-Checked "Frontend lint" { npm run lint }
        Invoke-Checked "Frontend component tests" { npm run test:run }
        Invoke-Checked "Frontend production build" { npm run build }
        if (-not $SkipE2E) {
            Invoke-Checked "Playwright core E2E" { npm run test:e2e -- --reporter=line }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

Write-Host "`nAll verification checks passed." -ForegroundColor Green
