param(
    [switch]$SkipE2E,
    [switch]$SkipCoverage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$uv = Get-Command uv -ErrorAction SilentlyContinue
$python = $env:A3_PYTHON

if (-not $uv -and -not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Neither uv nor python is available. Run uv sync --dev first."
    }
    $python = $pythonCommand.Source
}

function Invoke-Python {
    param([string[]]$Arguments)
    if ($uv) {
        & $uv.Source run python @Arguments
    }
    else {
        & $python @Arguments
    }
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
    Invoke-Checked "Database migrations" { Invoke-Python @("-m", "alembic", "upgrade", "head") }
    Invoke-Checked "Python compile check" {
        Invoke-Python @("-m", "compileall", "-q", "app", "agents", "routers", "services", "main.py", "models.py")
    }
    Invoke-Checked "Backend lint" { Invoke-Python @("-m", "ruff", "check", "app", "tests") }
    Invoke-Checked "Backend type check" { Invoke-Python @("-m", "mypy", "app") }

    if ($SkipCoverage) {
        Invoke-Checked "Backend tests" { Invoke-Python @("-m", "pytest", "-q") }
    }
    else {
        Invoke-Checked "Backend tests and core coverage" {
            Invoke-Python @(
                "-m", "pytest",
                "--cov=app.modules.courses.service",
                "--cov=app.modules.materials.service",
                "--cov=app.modules.learning.service",
                "--cov=app.modules.agent.service",
                "--cov=app.modules.agent.native_tool_agent",
                "--cov=app.modules.agent.router",
                "--cov=app.jobs.material_index_job",
                "--cov-fail-under=70",
                "--cov-report=term-missing",
                "-q"
            )
        }
    }

    Push-Location (Join-Path $root "frontend")
    try {
        Invoke-Checked "Frontend lint" { npm run lint }
        Invoke-Checked "Frontend component tests" { npm run test:run }
        Invoke-Checked "Frontend production build" { npm run build }
        if (-not $SkipE2E) {
            $previousPython = $env:A3_PYTHON
            if (-not $uv) {
                $env:A3_PYTHON = $python
            }
            try {
                Invoke-Checked "Playwright core E2E" { npm run test:e2e -- --reporter=line }
            }
            finally {
                $env:A3_PYTHON = $previousPython
            }
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
