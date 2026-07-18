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

function Invoke-BackendTestBatches {
    param([bool]$WithCoverage)

    # A fresh-database migration test starts its own interpreter. Running the whole
    # suite in one Windows process can otherwise retain SQLite/worker resources for
    # long enough that the OS terminates pytest before it reports a result. Keep the
    # public verification command deterministic while preserving aggregate coverage.
    $testFiles = @(
        Get-ChildItem (Join-Path $root "tests") -File -Filter "test_*.py" |
            Sort-Object Name |
            Select-Object -ExpandProperty FullName
    )
    $freshDatabaseTest = $testFiles | Where-Object { (Split-Path -Leaf $_) -eq "test_fresh_database_migrations.py" }
    $remainingTests = $testFiles | Where-Object { $_ -notin $freshDatabaseTest }
    $orderedTests = @($freshDatabaseTest) + @($remainingTests)
    $batchSize = 7

    if ($WithCoverage) {
        Invoke-Checked "Reset backend coverage data" { Invoke-Python @("-m", "coverage", "erase") }
    }

    for ($offset = 0; $offset -lt $orderedTests.Count; $offset += $batchSize) {
        $lastIndex = [Math]::Min($offset + $batchSize - 1, $orderedTests.Count - 1)
        $batch = @($orderedTests[$offset..$lastIndex])
        $batchNumber = [Math]::Floor($offset / $batchSize) + 1
        $arguments = @("-m", "pytest", "-q") + $batch

        if ($WithCoverage) {
            $arguments += @(
                "--cov=app.modules.courses.service",
                "--cov=app.modules.materials.service",
                "--cov=app.modules.learning.service",
                "--cov=app.modules.agent.service",
                "--cov=app.modules.agent.native_tool_agent",
                "--cov=app.modules.agent.router",
                "--cov=app.jobs.material_index_job",
                "--cov-append",
                "--cov-report="
            )
        }

        Invoke-Checked "Backend tests batch $batchNumber" { Invoke-Python $arguments }
    }

    if ($WithCoverage) {
        Invoke-Checked "Backend aggregate core coverage" {
            Invoke-Python @("-m", "coverage", "report", "--fail-under=70", "--show-missing")
        }
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

    Invoke-BackendTestBatches -WithCoverage (-not $SkipCoverage)

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
