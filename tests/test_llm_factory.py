import pytest

from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.factory import get_provider
from app.llm.openai_compatible_provider import OpenAICompatibleProvider


def make_settings(**overrides) -> Settings:
    base = dict(
        telegram_bot_token="123:test",
        telegram_start_secret="secret",
        database_url="sqlite+aiosqlite:///:memory:",
        llm_provider="anthropic",
        llm_model="test-model",
        llm_api_key="test-key",
    )
    base.update(overrides)
    return Settings(**base)


def test_get_provider_returns_anthropic_adapter():
    provider = get_provider(make_settings(llm_provider="anthropic"))
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_returns_openai_compatible_adapter():
    provider = get_provider(
        make_settings(llm_provider="openai_compatible", llm_base_url="https://api.deepseek.com")
    )
    assert isinstance(provider, OpenAICompatibleProvider)


def test_get_provider_raises_on_unknown_provider():
    with pytest.raises(ValueError):
        get_provider(make_settings(llm_provider="bogus"))
