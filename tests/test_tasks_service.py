from datetime import date, datetime, timedelta, timezone

from app.models import Task, TaskStatus, TaskTier, User
from app.services.tasks import (
    clear_all_open_tasks,
    mark_done,
    reopen,
    reschedule,
    rollover_backlog,
)


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


async def test_mark_done_sets_status_and_completed_at(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id)

    result = await mark_done(session, user.id, task.id)

    assert result.status == TaskStatus.done
    assert result.completed_at is not None


async def test_mark_done_returns_none_for_wrong_user(session):
    user = await _seed_user(session)
    other = await _seed_user(session, telegram_chat_id=2)
    task = await _seed_task(session, user.id)

    assert await mark_done(session, other.id, task.id) is None


async def test_mark_done_returns_none_if_already_done(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id, status=TaskStatus.done, completed_at=datetime.now(timezone.utc))

    assert await mark_done(session, user.id, task.id) is None


async def test_mark_done_returns_none_for_missing_task_id(session):
    user = await _seed_user(session)
    assert await mark_done(session, user.id, None) is None
    assert await mark_done(session, user.id, 999999) is None


async def test_reopen_clears_completed_at_and_reverts_status(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, status=TaskStatus.done, completed_at=datetime.now(timezone.utc)
    )

    result = await reopen(session, user.id, task.id)

    assert result.status == TaskStatus.open
    assert result.completed_at is None


async def test_reopen_clears_dismissed_at_and_reverts_status(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, status=TaskStatus.dismissed, dismissed_at=datetime.now(timezone.utc)
    )

    result = await reopen(session, user.id, task.id)

    assert result.status == TaskStatus.open
    assert result.dismissed_at is None


async def test_reopen_returns_none_if_task_not_closed(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id, status=TaskStatus.open)

    assert await reopen(session, user.id, task.id) is None


async def test_reschedule_updates_due_date_and_clears_reminded_at(session):
    user = await _seed_user(session)
    task = await _seed_task(
        session, user.id, due_date=date(2026, 7, 25), reminded_at=datetime.now(timezone.utc)
    )

    result = await reschedule(session, user.id, task.id, date(2026, 8, 1))

    assert result.due_date == date(2026, 8, 1)
    assert result.reminded_at is None


async def test_reschedule_returns_none_for_non_open_task(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id, status=TaskStatus.done)

    assert await reschedule(session, user.id, task.id, date(2026, 8, 1)) is None


async def test_reschedule_returns_none_for_missing_new_due_date(session):
    user = await _seed_user(session)
    task = await _seed_task(session, user.id)

    assert await reschedule(session, user.id, task.id, None) is None


async def test_rollover_backlog_shifts_due_dates_by_seven_days_and_returns_count(session):
    user = await _seed_user(session)
    today = date.today()
    overdue1 = await _seed_task(session, user.id, due_date=today - timedelta(days=3))
    overdue2 = await _seed_task(session, user.id, due_date=today - timedelta(days=10))

    count = await rollover_backlog(session, user.id)

    assert count == 2
    await session.refresh(overdue1)
    await session.refresh(overdue2)
    assert overdue1.due_date == today - timedelta(days=3) + timedelta(days=7)
    assert overdue2.due_date == today - timedelta(days=10) + timedelta(days=7)


async def test_rollover_backlog_ignores_future_and_dateless_tasks(session):
    user = await _seed_user(session)
    today = date.today()
    future = await _seed_task(session, user.id, due_date=today + timedelta(days=5))
    dateless = await _seed_task(session, user.id, due_date=None)

    count = await rollover_backlog(session, user.id)

    assert count == 0
    await session.refresh(future)
    await session.refresh(dateless)
    assert future.due_date == today + timedelta(days=5)
    assert dateless.due_date is None


async def test_clear_all_open_tasks_dismisses_only_open_tasks(session):
    user = await _seed_user(session)
    open1 = await _seed_task(session, user.id, title="a")
    open2 = await _seed_task(session, user.id, title="b")
    already_done = await _seed_task(
        session, user.id, title="c", status=TaskStatus.done, completed_at=datetime.now(timezone.utc)
    )

    count = await clear_all_open_tasks(session, user.id)

    assert count == 2
    await session.refresh(open1)
    await session.refresh(open2)
    await session.refresh(already_done)
    assert open1.status == TaskStatus.dismissed
    assert open1.dismissed_at is not None
    assert open2.status == TaskStatus.dismissed
    assert already_done.status == TaskStatus.done  # untouched
