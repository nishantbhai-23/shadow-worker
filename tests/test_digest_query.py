from datetime import date, timedelta

import pytest

from app.models import Task, TaskStatus, TaskTier, User
from app.services.digest import get_digest

TODAY = date(2026, 7, 22)


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    import app.services.digest as digest_module

    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(digest_module, "date", FixedDate)


async def _seed(session):
    user = User(telegram_chat_id=1)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    tasks = [
        Task(user_id=user.id, title="overdue call", tier=TaskTier.someday, due_date=TODAY - timedelta(days=1)),
        Task(user_id=user.id, title="due this week", tier=TaskTier.someday, due_date=TODAY + timedelta(days=3)),
        Task(user_id=user.id, title="due this month", tier=TaskTier.someday, due_date=TODAY + timedelta(days=20)),
        Task(user_id=user.id, title="no date, someday", tier=TaskTier.someday, due_date=None),
        Task(user_id=user.id, title="already done", tier=TaskTier.today, due_date=TODAY, status=TaskStatus.done),
    ]
    session.add_all(tasks)
    await session.commit()
    return user


async def test_today_bucket_includes_only_overdue_and_today(session):
    user = await _seed(session)
    text = await get_digest(session, user.id, "today")
    assert "overdue call" in text
    assert "due this week" not in text
    assert "already done" not in text  # status=done is excluded


async def test_week_bucket_rolls_up_today(session):
    user = await _seed(session)
    text = await get_digest(session, user.id, "week")
    assert "overdue call" in text
    assert "due this week" in text
    assert "due this month" not in text


async def test_month_bucket_rolls_up_today_and_week(session):
    user = await _seed(session)
    text = await get_digest(session, user.id, "month")
    assert "overdue call" in text
    assert "due this week" in text
    assert "due this month" in text
    assert "no date, someday" not in text


async def test_someday_bucket_is_dateless_fallback_only(session):
    user = await _seed(session)
    text = await get_digest(session, user.id, "someday")
    assert "no date, someday" in text
    assert "overdue call" not in text


async def test_empty_bucket_returns_placeholder(session):
    user = User(telegram_chat_id=2)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    text = await get_digest(session, user.id, "today")
    assert text == "Nothing here."


async def test_unknown_bucket_raises(session):
    user = User(telegram_chat_id=3)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    with pytest.raises(ValueError):
        await get_digest(session, user.id, "yesterday")
