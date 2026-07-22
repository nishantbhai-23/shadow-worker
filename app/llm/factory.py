from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.openai_compatible_provider import OpenAICompatibleProvider


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.llm_api_key, settings.llm_model)
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(
            settings.llm_api_key, settings.llm_model, settings.llm_base_url
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
