"""Central model construction for every LangChain agent."""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations.llm.mock_course_model import MockCourseChatModel


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return the single OpenAI-compatible chat model used by application agents."""
    settings = get_settings()
    if settings.mock_llm:
        return MockCourseChatModel()
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    if not settings.deepseek_base_url:
        raise RuntimeError("DEEPSEEK_BASE_URL 未配置")
    if not settings.deepseek_model:
        raise RuntimeError("DEEPSEEK_MODEL 未配置")
    return ChatOpenAI(
        api_key=SecretStr(settings.deepseek_api_key),
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
