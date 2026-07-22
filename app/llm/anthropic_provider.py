from anthropic import AsyncAnthropic

from app.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text
