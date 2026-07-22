from datetime import date, timedelta

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


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "Nothing here."
    lines = []
    for t in tasks:
        due = f" (due {t.due_date.isoformat()})" if t.due_date else ""
        lines.append(f"- {t.title}{due}")
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
