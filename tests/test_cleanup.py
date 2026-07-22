from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models import ContentType, Task, TaskStatus, TaskTier, Thought, ThoughtStatus, User
from app.services.cleanup import cleanup_closed_tasks, cleanup_old_thoughts

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


async def _seed_user(session, telegram_chat_id=1):
    user = User(telegram_chat_id=telegram_chat_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _seed_task(session, user_id, **kwargs):
    defaults = dict(title="t", tier=TaskTier.today, status=TaskStatus.open)
    defaults.update(kwargs)
    task = Task(user_id=user_id, **defaults)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _seed_thought(session, user_id, **kwargs):
    defaults = dict(content_type=ContentType.text, raw_text="x", status=ThoughtStatus.processed)
    defaults.update(kwargs)
    thought = Thought(user_id=user_id, **defaults)
    session.add(thought)
    await session.commit()
    await session.refresh(thought)
    return thought


async def test_cleanup_closed_tasks_deletes_done_past_ttl(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, status=TaskStatus.done, completed_at=NOW - timedelta(days=8)
    )

    count = await cleanup_closed_tasks(session, NOW)

    assert count == 1
    assert await session.get(Task, task.id) is None


async def test_cleanup_closed_tasks_deletes_dismissed_past_ttl(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, status=TaskStatus.dismissed, dismissed_at=NOW - timedelta(days=8)
    )

    count = await cleanup_closed_tasks(session, NOW)

    assert count == 1
    assert await session.get(Task, task.id) is None


async def test_cleanup_closed_tasks_keeps_within_ttl(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, status=TaskStatus.done, completed_at=NOW - timedelta(days=3)
    )

    count = await cleanup_closed_tasks(session, NOW)

    assert count == 0
    assert await session.get(Task, task.id) is not None


async def test_cleanup_closed_tasks_never_touches_open_tasks(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id, status=TaskStatus.open)

    count = await cleanup_closed_tasks(session, NOW)

    assert count == 0
    assert await session.get(Task, task.id) is not None


async def test_cleanup_old_thoughts_deletes_processed_past_ttl(session):
    user = await _seed_user(session)
    thought = await _seed_thought(
        session, user.id, status=ThoughtStatus.processed, created_at=NOW - timedelta(days=15)
    )

    count = await cleanup_old_thoughts(session, NOW)

    assert count == 1
    assert await session.get(Thought, thought.id) is None


async def test_cleanup_old_thoughts_deletes_error_past_ttl(session):
    user = await _seed_user(session)
    thought = await _seed_thought(
        session, user.id, status=ThoughtStatus.error, created_at=NOW - timedelta(days=15)
    )

    count = await cleanup_old_thoughts(session, NOW)

    assert count == 1
    assert await session.get(Thought, thought.id) is None


async def test_cleanup_old_thoughts_keeps_within_ttl(session):
    user = await _seed_user(session)
    thought = await _seed_thought(
        session, user.id, status=ThoughtStatus.processed, created_at=NOW - timedelta(days=5)
    )

    count = await cleanup_old_thoughts(session, NOW)

    assert count == 0
    assert await session.get(Thought, thought.id) is not None


async def test_cleanup_old_thoughts_never_touches_pending(session):
    user = await _seed_user(session)
    thought = await _seed_thought(
        session, user.id, status=ThoughtStatus.pending, created_at=NOW - timedelta(days=30)
    )

    count = await cleanup_old_thoughts(session, NOW)

    assert count == 0
    assert await session.get(Thought, thought.id) is not None


async def test_cleanup_old_thoughts_nulls_out_surviving_task_thought_id(session):
    user = await _seed_user(session)
    thought = await _seed_thought(
        session, user.id, status=ThoughtStatus.processed, created_at=NOW - timedelta(days=15)
    )
    task = await _seed_task(session, user.id, thought_id=thought.id, status=TaskStatus.open)

    count = await cleanup_old_thoughts(session, NOW)

    assert count == 1
    await session.refresh(task)
    assert task.thought_id is None
    assert task.status == TaskStatus.open  # the task itself survives
