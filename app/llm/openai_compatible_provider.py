from openai import AsyncOpenAI

from app.llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Covers DeepSeek's hosted API and self-hosted Ollama (both expose /v1/chat/completions)."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content
