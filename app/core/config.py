import os
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_network

from dotenv import load_dotenv

load_dotenv()


_PLACEHOLDER_VALUES = {
    "",
    "your_password",
    "your_secret_key",
    "your_api_key",
}
PRODUCTION_LEGACY_ROUTES_ERROR = (
    "生产环境禁止启用旧版路由，请设置 ENABLE_LEGACY_ROUTES=false"
)
_ENVIRONMENT_ALIASES = {
    "dev": "development",
    "development": "development",
    "test": "test",
    "testing": "test",
    "prod": "production",
    "production": "production",
    "stage": "production",
    "staging": "production",
}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name, "true" if default else "false").lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise RuntimeError(f"{name} 必须是 true/false、1/0、yes/no 或 on/off")


def _environment() -> str:
    raw = _env("APP_ENV", "development").lower()
    try:
        return _ENVIRONMENT_ALIASES[raw]
    except KeyError as exc:
        allowed = ", ".join(sorted(_ENVIRONMENT_ALIASES))
        raise RuntimeError(f"APP_ENV 无效：{raw!r}；允许值：{allowed}") from exc


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
    trusted_proxy_cidrs: tuple[str, ...]
    enable_legacy_routes: bool
    agent_tool_lease_seconds: float
    agent_action_lease_seconds: float
    agent_lease_heartbeat_seconds: float
    learning_memory_worker_enabled: bool
    learning_memory_worker_poll_seconds: float
    learning_memory_job_lease_seconds: float
    learning_memory_job_max_attempts: int
    auto_memory_min_confidence: float
    auto_memory_max_per_turn: int
    memory_relevance_threshold: float
    profile_aggregation_debounce_seconds: int
    profile_min_memory_count: int
    profile_min_course_count: int
    fast_rag_enabled: bool
    fast_rag_confidence_threshold: float
    fast_rag_max_anchors: int
    fast_rag_neighbor_window: int
    fast_rag_min_retrieval_score: float
    agent_context_budget_tokens: int
    agent_min_recent_rounds: int
    agent_target_recent_rounds: int
    conversation_summary_batch_rounds: int
    conversation_summary_max_tokens: int
    conversation_summary_max_blocks: int
    conversation_summary_compact_batch_size: int

    @classmethod
    def from_env(cls) -> "Settings":
        environment = _environment()
        return cls(
            app_name=_env("APP_NAME", "A3 专科学习 AI"),
            app_version=_env("APP_VERSION", "1.0.0"),
            environment=environment,
            database_host=_env("DATABASE_HOST", _env("DB_HOST", "127.0.0.1")),
            database_port=int(_env("DATABASE_PORT", _env("DB_PORT", "3306"))),
            database_user=_env("DATABASE_USER", _env("DB_USER", "root")),
            database_password=_env("DATABASE_PASSWORD", _env("DB_PASSWORD")),
            database_name=_env("DATABASE_NAME", _env("DB_NAME", "task_db2")),
            secret_key=_env("SECRET_KEY"),
            algorithm=_env("ALGORITHM", "HS256"),
            access_token_expire_hours=int(_env("ACCESS_TOKEN_EXPIRE_HOURS", "168")),
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
            trusted_proxy_cidrs=tuple(
                item.strip()
                for item in _env(
                    "TRUSTED_PROXY_CIDRS",
                    "127.0.0.1/32,::1/128",
                ).split(",")
                if item.strip()
            ),
            enable_legacy_routes=_env_bool(
                "ENABLE_LEGACY_ROUTES",
                default=environment != "production",
            ),
            agent_tool_lease_seconds=float(_env("AGENT_TOOL_LEASE_SECONDS", "180")),
            agent_action_lease_seconds=float(_env("AGENT_ACTION_LEASE_SECONDS", "180")),
            agent_lease_heartbeat_seconds=float(_env("AGENT_LEASE_HEARTBEAT_SECONDS", "30")),
            learning_memory_worker_enabled=_env_bool("LEARNING_MEMORY_WORKER_ENABLED", default=True),
            learning_memory_worker_poll_seconds=float(_env("LEARNING_MEMORY_WORKER_POLL_SECONDS", "5")),
            learning_memory_job_lease_seconds=float(_env("LEARNING_MEMORY_JOB_LEASE_SECONDS", "180")),
            learning_memory_job_max_attempts=int(_env("LEARNING_MEMORY_JOB_MAX_ATTEMPTS", "3")),
            auto_memory_min_confidence=float(_env("AUTO_MEMORY_MIN_CONFIDENCE", "0.85")),
            auto_memory_max_per_turn=int(_env("AUTO_MEMORY_MAX_PER_TURN", "2")),
            memory_relevance_threshold=float(_env("MEMORY_RELEVANCE_THRESHOLD", "0.20")),
            profile_aggregation_debounce_seconds=int(
                _env("PROFILE_AGGREGATION_DEBOUNCE_SECONDS", "300")
            ),
            profile_min_memory_count=int(_env("PROFILE_MIN_MEMORY_COUNT", "3")),
            profile_min_course_count=int(_env("PROFILE_MIN_COURSE_COUNT", "2")),
            fast_rag_enabled=_env_bool("FAST_RAG_ENABLED", default=True),
            fast_rag_confidence_threshold=float(_env("FAST_RAG_CONFIDENCE_THRESHOLD", "0.85")),
            fast_rag_max_anchors=int(_env("FAST_RAG_MAX_ANCHORS", "3")),
            fast_rag_neighbor_window=int(_env("FAST_RAG_NEIGHBOR_WINDOW", "1")),
            fast_rag_min_retrieval_score=float(_env("FAST_RAG_MIN_RETRIEVAL_SCORE", "0.10")),
            agent_context_budget_tokens=int(_env("AGENT_CONTEXT_BUDGET_TOKENS", "10000")),
            agent_min_recent_rounds=int(_env("AGENT_MIN_RECENT_ROUNDS", "3")),
            agent_target_recent_rounds=int(_env("AGENT_TARGET_RECENT_ROUNDS", "5")),
            conversation_summary_batch_rounds=int(_env("CONVERSATION_SUMMARY_BATCH_ROUNDS", "4")),
            conversation_summary_max_tokens=int(_env("CONVERSATION_SUMMARY_MAX_TOKENS", "3000")),
            conversation_summary_max_blocks=int(_env("CONVERSATION_SUMMARY_MAX_BLOCKS", "8")),
            conversation_summary_compact_batch_size=int(_env("CONVERSATION_SUMMARY_COMPACT_BATCH_SIZE", "4")),
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

        if self.environment == "production" and self.enable_legacy_routes:
            errors.append(PRODUCTION_LEGACY_ROUTES_ERROR)

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

        if self.agent_tool_lease_seconds <= 0:
            errors.append("AGENT_TOOL_LEASE_SECONDS 必须大于 0")

        if self.agent_action_lease_seconds <= 0:
            errors.append("AGENT_ACTION_LEASE_SECONDS 必须大于 0")

        if self.agent_lease_heartbeat_seconds <= 0:
            errors.append("AGENT_LEASE_HEARTBEAT_SECONDS 必须大于 0")
        elif self.agent_lease_heartbeat_seconds > (
            min(
                self.agent_tool_lease_seconds,
                self.agent_action_lease_seconds,
            )
            / 3
            + 1e-9
        ):
            errors.append(
                "AGENT_LEASE_HEARTBEAT_SECONDS 必须不大于最短 Agent 租约的三分之一"
            )

        if self.learning_memory_worker_poll_seconds <= 0:
            errors.append("LEARNING_MEMORY_WORKER_POLL_SECONDS 必须大于 0")

        if self.learning_memory_job_lease_seconds <= 0:
            errors.append("LEARNING_MEMORY_JOB_LEASE_SECONDS 必须大于 0")

        if self.learning_memory_job_max_attempts < 1:
            errors.append("LEARNING_MEMORY_JOB_MAX_ATTEMPTS 必须至少为 1")

        if not 0 <= self.auto_memory_min_confidence <= 1:
            errors.append("AUTO_MEMORY_MIN_CONFIDENCE 必须在 0 到 1 之间")

        if self.auto_memory_max_per_turn < 1:
            errors.append("AUTO_MEMORY_MAX_PER_TURN 必须至少为 1")

        if not 0 <= self.memory_relevance_threshold <= 1:
            errors.append("MEMORY_RELEVANCE_THRESHOLD 必须在 0 到 1 之间")

        if self.profile_aggregation_debounce_seconds < 0:
            errors.append("PROFILE_AGGREGATION_DEBOUNCE_SECONDS 不能小于 0")

        if self.profile_min_memory_count < 1:
            errors.append("PROFILE_MIN_MEMORY_COUNT 必须至少为 1")

        if self.profile_min_course_count < 1:
            errors.append("PROFILE_MIN_COURSE_COUNT 必须至少为 1")

        if not 0 <= self.fast_rag_confidence_threshold <= 1:
            errors.append("FAST_RAG_CONFIDENCE_THRESHOLD 必须在 0 到 1 之间")
        if not 1 <= self.fast_rag_max_anchors <= 5:
            errors.append("FAST_RAG_MAX_ANCHORS 必须在 1 到 5 之间")
        if not 0 <= self.fast_rag_neighbor_window <= 2:
            errors.append("FAST_RAG_NEIGHBOR_WINDOW 必须在 0 到 2 之间")
        if not 0 <= self.fast_rag_min_retrieval_score <= 1:
            errors.append("FAST_RAG_MIN_RETRIEVAL_SCORE 必须在 0 到 1 之间")

        if self.agent_context_budget_tokens < 2_000:
            errors.append("AGENT_CONTEXT_BUDGET_TOKENS 必须至少为 2000")
        if not 1 <= self.agent_min_recent_rounds <= 5:
            errors.append("AGENT_MIN_RECENT_ROUNDS 必须在 1 到 5 之间")
        if not self.agent_min_recent_rounds <= self.agent_target_recent_rounds <= 8:
            errors.append("AGENT_TARGET_RECENT_ROUNDS 必须不小于最小轮次且不大于 8")
        if self.conversation_summary_batch_rounds < 1:
            errors.append("CONVERSATION_SUMMARY_BATCH_ROUNDS 必须至少为 1")
        if self.conversation_summary_max_tokens < 300:
            errors.append("CONVERSATION_SUMMARY_MAX_TOKENS 必须至少为 300")
        if self.conversation_summary_max_blocks < 2:
            errors.append("CONVERSATION_SUMMARY_MAX_BLOCKS 必须至少为 2")
        if self.conversation_summary_compact_batch_size < 2:
            errors.append("CONVERSATION_SUMMARY_COMPACT_BATCH_SIZE 必须至少为 2")

        for cidr in self.trusted_proxy_cidrs:
            try:
                ip_network(cidr, strict=False)
            except ValueError:
                errors.append(f"TRUSTED_PROXY_CIDRS contains an invalid network: {cidr}")

        if errors:
            raise RuntimeError("启动配置无效：" + "；".join(errors))

    def validate_route_policy(self) -> None:
        if self.environment == "production" and self.enable_legacy_routes:
            raise RuntimeError("启动配置无效：" + PRODUCTION_LEGACY_ROUTES_ERROR)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
