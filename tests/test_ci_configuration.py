from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_playwright_uses_bundled_chromium_and_cross_platform_python():
    config = (ROOT_DIR / "frontend" / "playwright.config.js").read_text(encoding="utf-8")
    setup = (ROOT_DIR / "frontend" / "e2e" / "global-setup.js").read_text(encoding="utf-8")
    teardown = (ROOT_DIR / "frontend" / "e2e" / "global-teardown.js").read_text(
        encoding="utf-8"
    )

    assert "channel: 'chrome'" not in config
    assert ".venv\\\\Scripts\\\\python.exe" not in config + setup + teardown
    assert "uv run python scripts/run_e2e_backend.py" in config
    assert "--require-test-database" in setup
    assert "--require-test-database" in teardown


def test_ci_runs_all_required_verification_layers():
    workflow = (ROOT_DIR / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert '"feature/**"' in workflow
    assert "uv run alembic upgrade head" in workflow
    assert "npm run test:run" in workflow
    assert "npm run build" in workflow
    assert "playwright install --with-deps chromium" in workflow
    assert "npm run test:e2e" in workflow
    assert "actions/upload-artifact@v4" in workflow
