from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock

from sqlmodel import select

import app.services.triage as triage_module
from app.models import ContentType, Task, TaskStatus, TaskTier, Thought, ThoughtStatus, User


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[str] = []

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(user_prompt)
        return self._response


async def _seed_pending_thought(session, raw_text="call the dentist by friday", telegram_chat_id=1):
    user = User(telegram_chat_id=telegram_chat_id)
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


async def _seed_open_task(session, user_id, title="Call the dentist"):
    task = Task(user_id=user_id, title=title, tier=TaskTier.today, status=TaskStatus.open)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_process_thought_creates_tasks_from_valid_json(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '{"intent": "new_task", "tasks": '
        '[{"title": "Call the dentist", "due_date": "2026-07-25", "due_time": null, "tier": "today"}]}'
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


async def test_process_thought_extracts_due_time(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '{"intent": "new_task", "tasks": '
        '[{"title": "Call mom", "due_date": "2026-07-25", "due_time": "15:00", "tier": "today"}]}'
    )
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session, raw_text="call mom at 3pm")
    await triage_module.process_thought(thought.id)

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    tasks = result.all()
    assert tasks[0].due_time == time(15, 0)


async def test_process_thought_defaults_due_date_to_today_when_only_due_time_given(
    session, session_maker, monkeypatch
):
    """Defensive fallback: a bare time with no date (e.g. the model still returns
    due_date: null despite the prompt's instruction) must default to today, since the
    reminder sweep requires both due_date and due_time to be set to ever fire."""
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '{"intent": "new_task", "tasks": '
        '[{"title": "Call Nonu", "due_date": null, "due_time": "20:30", "tier": null}]}'
    )
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session, raw_text="call Nonu at 8:30pm")
    await triage_module.process_thought(thought.id)

    result = await session.exec(select(Task).where(Task.thought_id == thought.id))
    tasks = result.all()
    assert tasks[0].due_time == time(20, 30)
    assert tasks[0].due_date == date.today()


async def test_process_thought_handles_explicit_null_tier_when_due_date_present(session, session_maker, monkeypatch):
    """Real models (observed with DeepSeek) sometimes return "tier": null, not just
    an omitted key, once due_date is set -- the prompt says tier is a fallback only."""
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider(
        '{"intent": "new_task", "tasks": '
        '[{"title": "Call the dentist", "due_date": "2026-07-25", "due_time": null, "tier": null}]}'
    )
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
        '{"intent": "new_task", "tasks": ['
        '{"title": "Call the dentist", "due_date": null, "due_time": null, "tier": "today"}, '
        '{"title": "Buy milk", "due_date": null, "due_time": null, "tier": "week"}]}'
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
    fake = FakeProvider('{"intent": "new_task", "tasks": []}')
    monkeypatch.setattr(triage_module, "_provider", fake)

    _, thought = await _seed_pending_thought(session)
    thought.status = ThoughtStatus.processed
    session.add(thought)
    await session.commit()

    await triage_module.process_thought(thought.id)

    assert fake.calls == []  # never even asked the LLM


async def test_process_pending_thoughts_skips_voice_without_text(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)
    fake = FakeProvider('{"intent": "new_task", "tasks": []}')
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


async def test_process_thought_mark_done_updates_task_and_sends_message(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)

    user, thought = await _seed_pending_thought(session, raw_text="finally called the dentist", telegram_chat_id=42)
    task = await _seed_open_task(session, user.id)

    fake = FakeProvider(f'{{"intent": "mark_done", "task_id": {task.id}}}')
    monkeypatch.setattr(triage_module, "_provider", fake)

    bot = AsyncMock()
    await triage_module.process_thought(thought.id, bot=bot)

    await session.refresh(task)
    assert task.status == TaskStatus.done
    assert task.completed_at is not None

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 42
    assert "Call the dentist" in kwargs["text"]


async def test_process_thought_mark_done_unknown_task_id_is_quiet_noop(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)

    _, thought = await _seed_pending_thought(session, raw_text="finished something")
    fake = FakeProvider('{"intent": "mark_done", "task_id": 999999}')
    monkeypatch.setattr(triage_module, "_provider", fake)

    bot = AsyncMock()
    await triage_module.process_thought(thought.id, bot=bot)

    await session.refresh(thought)
    assert thought.status == ThoughtStatus.processed
    bot.send_message.assert_not_awaited()


async def test_process_thought_reschedule_updates_due_date_and_clears_reminded_at(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)

    user, thought = await _seed_pending_thought(session, raw_text="push the dentist to next week", telegram_chat_id=42)
    task = await _seed_open_task(session, user.id)
    task.due_date = date(2026, 7, 25)
    task.reminded_at = datetime.now(timezone.utc)
    session.add(task)
    await session.commit()

    fake = FakeProvider(
        f'{{"intent": "reschedule", "task_id": {task.id}, "new_due_date": "2026-08-01"}}'
    )
    monkeypatch.setattr(triage_module, "_provider", fake)

    bot = AsyncMock()
    await triage_module.process_thought(thought.id, bot=bot)

    await session.refresh(task)
    assert task.due_date == date(2026, 8, 1)
    assert task.reminded_at is None
    bot.send_message.assert_awaited_once()
    assert "2026-08-01" in bot.send_message.await_args.kwargs["text"]


async def test_process_thought_reopen_dismissed_task(session, session_maker, monkeypatch):
    monkeypatch.setattr(triage_module, "async_session_maker", session_maker)

    user, thought = await _seed_pending_thought(session, raw_text="reopen the dentist thing", telegram_chat_id=42)
    task = await _seed_open_task(session, user.id)
    task.status = TaskStatus.dismissed
    task.dismissed_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.add(task)
    await session.commit()

    fake = FakeProvider(f'{{"intent": "reopen", "task_id": {task.id}}}')
    monkeypatch.setattr(triage_module, "_provider", fake)

    bot = AsyncMock()
    await triage_module.process_thought(thought.id, bot=bot)

    await session.refresh(task)
    assert task.status == TaskStatus.open
    assert task.dismissed_at is None
    bot.send_message.assert_awaited_once()
