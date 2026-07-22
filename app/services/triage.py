import json
from datetime import date, datetime, timezone

from sqlmodel import select

from app.config import settings
from app.db import async_session_maker
from app.llm.factory import get_provider
from app.llm.prompts import build_triage_system_prompt
from app.models import Task, TaskTier, Thought, ThoughtStatus

_provider = None


def _get_provider():
    global _provider
    if _provider is None:
        _provider = get_provider(settings)
    return _provider


async def process_thought(thought_id: int) -> None:
    """Triage a single pending Thought into Task row(s). Self-contained: takes just an id,
    so it can be called from a poller today or a real queue consumer later without changing."""
    async with async_session_maker() as session:
        thought = await session.get(Thought, thought_id)
        if thought is None or thought.status != ThoughtStatus.pending:
            return

        provider = _get_provider()
        system_prompt = build_triage_system_prompt(date.today().isoformat())
        try:
            raw_response = await provider.complete(system_prompt, thought.raw_text or "")
            items = json.loads(raw_response)
            for item in items:
                raw_due_date = item.get("due_date")
                session.add(
                    Task(
                        user_id=thought.user_id,
                        thought_id=thought.id,
                        title=item["title"],
                        due_date=date.fromisoformat(raw_due_date) if raw_due_date else None,
                        tier=TaskTier(item.get("tier") or "someday"),
                    )
                )
            thought.status = ThoughtStatus.processed
            thought.processed_at = datetime.now(timezone.utc)
        except Exception as exc:
            thought.status = ThoughtStatus.error
            thought.error_message = str(exc)[:2000]

        session.add(thought)
        await session.commit()


async def process_pending_thoughts() -> None:
    """The worker: finds pending Thoughts with actual text and hands each id to
    process_thought(). This is the piece that gets swapped for a real queue consumer
    later. Voice thoughts stay pending (no raw_text yet) until a future transcription
    job fills in `transcript` — they're deliberately excluded here, not processed."""
    async with async_session_maker() as session:
        result = await session.exec(
            select(Thought.id).where(
                Thought.status == ThoughtStatus.pending,
                Thought.raw_text.is_not(None),
            )
        )
        pending_ids = result.all()

    for thought_id in pending_ids:
        await process_thought(thought_id)
