import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


_PLACEHOLDER_VALUES = {
    "",
    "your_password",
    "your_secret_key",
    "your_api_key",
}


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    database_host: str
    database_port: int
    database_user: str
    database_password: str
    database_name: str
    secret_key: str
    algorithm: str
    access_token_expire_hours: int
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    mock_llm: bool
    tavily_api_key: str
    youtube_api_key: str
    external_resource_timeout_seconds: float
    external_resource_cache_minutes: int
    auth_rate_limit_enabled: bool
    enable_legacy_routes: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=_env("APP_NAME", "A3 专科学习 AI"),
            app_version=_env("APP_VERSION", "1.0.0"),
            environment=_env("APP_ENV", "development").lower(),
            database_host=_env("DATABASE_HOST", _env("DB_HOST", "127.0.0.1")),
            database_port=int(_env("DATABASE_PORT", _env("DB_PORT", "3306"))),
            database_user=_env("DATABASE_USER", _env("DB_USER", "root")),
            database_password=_env("DATABASE_PASSWORD", _env("DB_PASSWORD")),
            database_name=_env("DATABASE_NAME", _env("DB_NAME", "task_db2")),
            secret_key=_env("SECRET_KEY"),
            algorithm=_env("ALGORITHM", "HS256"),
            access_token_expire_hours=int(_env("ACCESS_TOKEN_EXPIRE_HOURS", "2")),
            deepseek_api_key=_env("DEEPSEEK_API_KEY"),
            deepseek_base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=_env("DEEPSEEK_MODEL"),
            llm_timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", "30")),
            llm_max_retries=int(_env("LLM_MAX_RETRIES", "2")),
            mock_llm=_env_bool("A3_MOCK_LLM"),
            tavily_api_key=_env("TAVILY_API_KEY"),
            youtube_api_key=_env("YOUTUBE_API_KEY"),
            external_resource_timeout_seconds=float(
                _env("EXTERNAL_RESOURCE_TIMEOUT_SECONDS", "12")
            ),
            external_resource_cache_minutes=int(
                _env("EXTERNAL_RESOURCE_CACHE_MINUTES", "360")
            ),
            auth_rate_limit_enabled=_env_bool("AUTH_RATE_LIMIT_ENABLED", default=True),
            enable_legacy_routes=_env_bool(
                "ENABLE_LEGACY_ROUTES",
                default=_env("APP_ENV", "development").lower() != "production",
            ),
        )

    def validate_startup(self) -> None:
        errors = []

        required = {
            "DATABASE_HOST": self.database_host,
            "DATABASE_USER": self.database_user,
            "DATABASE_NAME": self.database_name,
            "SECRET_KEY": self.secret_key,
        }
        for name, value in required.items():
            if value.lower() in _PLACEHOLDER_VALUES:
                errors.append(f"{name} 未配置")

        if self.environment == "production" and len(self.secret_key) < 32:
            errors.append("生产环境 SECRET_KEY 长度必须至少为 32")

        if self.access_token_expire_hours < 1:
            errors.append("ACCESS_TOKEN_EXPIRE_HOURS 必须大于 0")

        if self.llm_timeout_seconds <= 0:
            errors.append("LLM_TIMEOUT_SECONDS 必须大于 0")

        if not 0 <= self.llm_max_retries <= 2:
            errors.append("LLM_MAX_RETRIES 必须在 0 到 2 之间")

        if self.external_resource_timeout_seconds <= 0:
            errors.append("EXTERNAL_RESOURCE_TIMEOUT_SECONDS 必须大于 0")

        if self.external_resource_cache_minutes < 1:
            errors.append("EXTERNAL_RESOURCE_CACHE_MINUTES 必须大于 0")

        if errors:
            raise RuntimeError("启动配置无效：" + "；".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
