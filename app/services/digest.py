from datetime import date, datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Task, TaskStatus

BUCKETS = ("today", "week", "month", "someday", "now")


def effective_tier(task: Task, today: date) -> str:
    """Coarse relative bucket: derived from due_date when set (more reliable than the
    model's own bucket arithmetic), falling back to the model's tier guess otherwise."""
    if task.due_date is not None:
        if task.due_date <= today:
            return "today"
        if task.due_date <= today + timedelta(days=7):
            return "week"
        if task.due_date <= today + timedelta(days=30):
            return "month"
        return "someday"
    return task.tier.value


async def _open_tasks(session: AsyncSession, user_id: int) -> list[Task]:
    result = await session.exec(
        select(Task).where(Task.user_id == user_id, Task.status == TaskStatus.open)
    )
    return list(result.all())


def _format_due(t: Task) -> str:
    if t.due_date and t.due_time:
        return f" (due {t.due_date.isoformat()} at {t.due_time.strftime('%H:%M')})"
    if t.due_date:
        return f" (due {t.due_date.isoformat()})"
    if t.due_time:
        return f" (at {t.due_time.strftime('%H:%M')})"
    return ""


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "Nothing here."
    lines = [f"- {t.title}{_format_due(t)}" for t in tasks]
    return "\n".join(lines)


async def get_digest(session: AsyncSession, user_id: int, bucket: str) -> str:
    if bucket not in BUCKETS:
        raise ValueError(f"Unknown bucket: {bucket}")

    today = date.today()
    tiered = [(t, effective_tier(t, today)) for t in await _open_tasks(session, user_id)]

    if bucket == "today":
        selected = [t for t, tier in tiered if tier == "today"]
    elif bucket == "week":
        selected = [t for t, tier in tiered if tier in ("today", "week")]
    elif bucket == "month":
        selected = [t for t, tier in tiered if tier in ("today", "week", "month")]
    elif bucket == "someday":
        selected = [t for t, tier in tiered if tier == "someday"]
    else:  # "now" — overdue first, then due today, then date-less-but-tier-today
        selected = sorted(
            (t for t, tier in tiered if tier == "today"),
            key=lambda t: t.due_date or date.max,
        )

    return _format_tasks(selected)


async def get_due_today(session: AsyncSession, user_id: int) -> str:
    """Used only by the unprompted daily push -- deliberately stricter than the
    on-demand /today command: only tasks with a real due_date (includes overdue),
    excluding dateless tier-guessed tasks. A proactive nag should be based on
    something the user actually committed to a date, not the model's own guess."""
    today = date.today()
    result = await session.exec(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == TaskStatus.open,
            Task.due_date.is_not(None),
            Task.due_date <= today,
        )
        .order_by(Task.due_date)
    )
    return _format_tasks(list(result.all()))


async def get_backlog(session: AsyncSession, user_id: int) -> str:
    """Overdue, still-open tasks. Deliberately bypasses effective_tier -- backlog is a
    distinct concept from the "today" bucket, which already conflates overdue with
    due-today."""
    today = date.today()
    result = await session.exec(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == TaskStatus.open,
            Task.due_date.is_not(None),
            Task.due_date < today,
        )
        .order_by(Task.due_date)
    )
    return _format_tasks(list(result.all()))


def _format_completed(tasks: list[Task]) -> str:
    if not tasks:
        return "Nothing here."
    lines = []
    for t in tasks:
        done_date = t.completed_at.date().isoformat() if t.completed_at else "?"
        lines.append(f"- {t.title} (done {done_date})")
    return "\n".join(lines)


async def get_completed(session: AsyncSession, user_id: int) -> str:
    """Tasks actually completed (not cleared/dismissed) in the last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = await session.exec(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == TaskStatus.done,
            Task.completed_at >= cutoff,
        )
        .order_by(Task.completed_at.desc())
    )
    return _format_completed(list(result.all()))
