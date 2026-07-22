from datetime import date

from sqlmodel import select

import app.services.triage as triage_module
from app.models import ContentType, Task, Thought, ThoughtStatus, User


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[str] = []

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(user_prompt)
        return self._response


async def _seed_pending_thought(session, raw_text="call the dentist by friday"):
    user = User(telegram_chat_id=1)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    thought = Thought(
        user_id=user.id,
        content_type=ContentType.text,
        raw_text=raw_text,
        status=ThoughtStatus.pending,
    )
    session.add(thought)
    await session.commit()
    await session.refresh(thought)
    return user, thought


async def test_process_thought_creates_tasks_from_valid_json(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '[{"title": "Call the dentist", "due_date": "2026-07-25", "tier": "today"}]'
    )
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session)
    await triage_module.process_thought(thought.id)

    await session.refresh(thought)
    assert thought.status == ThoughtStatus.processed
    assert thought.processed_at is not None

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    tasks = result.all()
    assert len(tasks) == 1
    assert tasks[0].title == "Call the dentist"
    assert tasks[0].due_date == date(2026, 7, 25)


async def test_process_thought_handles_explicit_null_tier_when_due_date_present(session, session_maker, monkeypatch):
    """Real models (observed with DeepSeek) sometimes return "tier": null, not just
    an omitted key, once due_date is set -- the prompt says tier is a fallback only."""
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider('[{"title": "Call the dentist", "due_date": "2026-07-25", "tier": null}]')
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session)
    await triage_module.process_thought(thought.id)

    await session.refresh(thought)
    assert thought.status == ThoughtStatus.processed

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    tasks = result.all()
    assert len(tasks) == 1
    assert tasks[0].due_date == date(2026, 7, 25)
    assert tasks[0].tier.value == "someday"


async def test_process_thought_creates_multiple_tasks_from_one_thought(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '[{"title": "Call the dentist", "due_date": null, "tier": "today"}, '
        '{"title": "Buy milk", "due_date": null, "tier": "week"}]'
    )
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session, raw_text="dentist and milk")
    await triage_module.process_thought(thought.id)

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    tasks = result.all()
    assert {t.title for t in tasks} == {"Call the dentist", "Buy milk"}


async def test_process_thought_marks_error_on_malformed_json(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    monkeypatch.setattr(triage_module, "_provider", FakeProvider("not valid json"))

    _, thought = await _seed_pending_thought(session)
    await triage_module.process_thought(thought.id)

    await session.refresh(thought)
    assert thought.status == ThoughtStatus.error
    assert thought.error_message is not None

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    assert result.all() == []


async def test_process_thought_is_noop_for_non_pending_thought(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider("[]")
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session)
    thought.status = ThoughtStatus.processed
    session.add(thought)
    await session.commit()

    await triage_module.process_thought(thought.id)

    assert fake.calls == []  # never even asked the LLM


async def test_process_pending_thoughts_skips_voice_without_text(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider("[]")
    monkeypatch.setattr(triage_module, "_provider", fake)

    user = User(telegram_chat_id=7)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    session.add(
        Thought(
            user_id=user.id,
            content_type=ContentType.voice,
            telegram_file_id="f1",
            status=ThoughtStatus.pending,
        )
    )
    session.add(
        Thought(
            user_id=user.id,
            content_type=ContentType.text,
            raw_text="hi",
            status=ThoughtStatus.pending,
        )
    )
    await session.commit()

    await triage_module.process_pending_thoughts()

    assert fake.calls == ["hi"]
