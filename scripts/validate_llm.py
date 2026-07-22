"""Throwaway script to sanity-check the configured LLM provider before wiring it into
the app. Run with real credentials in .env: python scripts/validate_llm.py
"""

import asyncio
from datetime import date

from app.config import settings
from app.llm.factory import get_provider
from app.llm.prompts import build_triage_system_prompt


async def main() -> None:
    provider = get_provider(settings)
    system_prompt = build_triage_system_prompt(date.today().isoformat())
    response = await provider.complete(
        system_prompt,
        "need to call the dentist by friday, also should really clean out my closet at some point",
    )
    print(f"Provider: {settings.llm_provider} / {settings.llm_model}")
    print("Raw response:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
