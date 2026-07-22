from datetime import date, datetime, time, timedelta, timezone

from app.models import Task, TaskStatus, TaskTier, User
from app.services.reminders import due_time_reminders

TZ = "UTC"


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


async def test_fires_within_ten_minute_window(session):
    user = await _seed_user(session)
    now = datetime(2026, 7, 23, 14, 55, tzinfo=timezone.utc)  # due at 15:00, 5 min out
    await _seed_task(session, user.id, due_date=date(2026, 7, 23), due_time=time(15, 0))

    to_send = await due_time_reminders(session, now, TZ)

    assert len(to_send) == 1
    assert to_send[0][1] == user.telegram_chat_id


async def test_skips_when_window_not_yet_reached(session):
    user = await _seed_user(session)
    now = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)  # due at 15:00, way early
    await _seed_task(session, user.id, due_date=date(2026, 7, 23), due_time=time(15, 0))

    to_send = await due_time_reminders(session, now, TZ)

    assert to_send == []


async def test_skips_already_reminded(session):
    user = await _seed_user(session)
    now = datetime(2026, 7, 23, 14, 55, tzinfo=timezone.utc)
    await _seed_task(
        session,
        user.id,
        due_date=date(2026, 7, 23),
        due_time=time(15, 0),
        reminded_at=datetime(2026, 7, 23, 14, 50, tzinfo=timezone.utc),
    )

    to_send = await due_time_reminders(session, now, TZ)

    assert to_send == []


async def test_skips_tasks_without_due_time(session):
    user = await _seed_user(session)
    now = datetime(2026, 7, 23, 14, 55, tzinfo=timezone.utc)
    await _seed_task(session, user.id, due_date=date(2026, 7, 23), due_time=None)

    to_send = await due_time_reminders(session, now, TZ)

    assert to_send == []


async def test_marks_reminded_but_suppresses_send_when_stale_over_24h(session):
    user = await _seed_user(session)
    # due_time was 2 days ago -- e.g. bot was down
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    task = await _seed_task(session, user.id, due_date=date(2026, 7, 21), due_time=time(15, 0))

    to_send = await due_time_reminders(session, now, TZ)

    assert to_send == []  # not sent...
    await session.refresh(task)
    assert task.reminded_at is not None  # ...but marked so it's never rechecked


async def test_skips_non_open_tasks(session):
    user = await _seed_user(session)
    now = datetime(2026, 7, 23, 14, 55, tzinfo=timezone.utc)
    await _seed_task(
        session,
        user.id,
        due_date=date(2026, 7, 23),
        due_time=time(15, 0),
        status=TaskStatus.done,
        completed_at=now,
    )

    to_send = await due_time_reminders(session, now, TZ)

    assert to_send == []
