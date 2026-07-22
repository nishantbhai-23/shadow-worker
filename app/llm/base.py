from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Single-shot completion. No streaming, no tools, no retries in v0."""
