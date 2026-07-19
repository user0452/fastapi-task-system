"""Central model construction for every LangChain agent."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations.llm.mock_course_model import MockCourseChatModel
from app.modules.account.llm_config_service import get_enabled_user_llm_config


def build_openai_compatible_model(*, api_key: str, base_url: str, model: str) -> BaseChatModel:
    settings = get_settings()
    return ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url=base_url,
        model=model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def get_llm(user_id: int | None = None) -> BaseChatModel:
    """Return a user override when enabled, otherwise the server OpenAI-compatible model."""
    settings = get_settings()
    if settings.mock_llm:
        return MockCourseChatModel()
    if user_id is not None:
        user_config = get_enabled_user_llm_config(user_id)
        if user_config is not None:
            return build_openai_compatible_model(**user_config)
    if not settings.deepseek_api_key:
        raise RuntimeError("服务端模型 API Key 未配置，请在设置中配置个人 API")
    if not settings.deepseek_base_url:
        raise RuntimeError("服务端模型 API 地址未配置，请在设置中配置个人 API")
    if not settings.deepseek_model:
        raise RuntimeError("服务端模型名称未配置，请在设置中配置个人 API")
    return build_openai_compatible_model(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


__all__ = ["build_openai_compatible_model", "get_llm"]
