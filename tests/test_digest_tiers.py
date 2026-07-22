from datetime import date, time, timedelta

import pytest

from app.models import Task, TaskTier
from app.services.digest import _format_due, effective_tier

TODAY = date(2026, 7, 22)


def make_task(due_date=None, tier=TaskTier.someday):
    return Task(user_id=1, title="t", tier=tier, due_date=due_date)


@pytest.mark.parametrize(
    ("due_date", "tier", "expected"),
    [
        (TODAY - timedelta(days=2), TaskTier.someday, "today"),  # overdue
        (TODAY, TaskTier.someday, "today"),
        (TODAY + timedelta(days=1), TaskTier.someday, "week"),
        (TODAY + timedelta(days=7), TaskTier.someday, "week"),  # boundary, inclusive
        (TODAY + timedelta(days=8), TaskTier.someday, "month"),
        (TODAY + timedelta(days=30), TaskTier.someday, "month"),  # boundary, inclusive
        (TODAY + timedelta(days=31), TaskTier.someday, "someday"),
        (None, TaskTier.today, "today"),  # no date -> falls back to model's tier
        (None, TaskTier.week, "week"),
        (None, TaskTier.month, "month"),
        (None, TaskTier.someday, "someday"),
    ],
)
def test_effective_tier(due_date, tier, expected):
    task = make_task(due_date=due_date, tier=tier)
    assert effective_tier(task, TODAY) == expected


def test_format_due_shows_date_and_time_together():
    task = Task(user_id=1, title="t", tier=TaskTier.today, due_date=TODAY, due_time=time(20, 30))
    assert _format_due(task) == " (due 2026-07-22 at 20:30)"


def test_format_due_date_only():
    task = Task(user_id=1, title="t", tier=TaskTier.today, due_date=TODAY)
    assert _format_due(task) == " (due 2026-07-22)"


def test_format_due_time_only_no_date():
    """Shouldn't normally happen after the triage-side fallback, but the formatter
    should degrade gracefully if it ever does."""
    task = Task(user_id=1, title="t", tier=TaskTier.today, due_time=time(20, 30))
    assert _format_due(task) == " (at 20:30)"


def test_format_due_neither_date_nor_time():
    task = Task(user_id=1, title="t", tier=TaskTier.someday)
    assert _format_due(task) == ""
