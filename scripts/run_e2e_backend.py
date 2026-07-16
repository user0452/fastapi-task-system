"""Create the disposable E2E database, migrate it, and start the API."""

# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ENABLE_LEGACY_ROUTES", "true")
os.environ.setdefault("A3_MOCK_LLM", "true")
os.environ.setdefault("A3_MOCK_EMBEDDING", "true")
os.environ.setdefault("AUTH_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault(
    "DATABASE_NAME",
    os.environ.get("A3_E2E_DATABASE_NAME", "a3_e2e_test"),
)

from app.core.schema import upgrade_database
from app.core.test_database import create_test_database, validate_test_database_name


def main() -> None:
    database_name = validate_test_database_name(os.environ["DATABASE_NAME"])
    create_test_database(database_name)
    upgrade_database()

    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8011)


if __name__ == "__main__":
    main()
