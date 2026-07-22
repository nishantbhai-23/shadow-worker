from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Task, TaskStatus, Thought, ThoughtStatus

CLOSED_TASK_TTL = timedelta(days=7)
OLD_THOUGHT_TTL = timedelta(days=14)


async def cleanup_closed_tasks(session: AsyncSession, now_utc: datetime) -> int:
    """Hard-deletes tasks completed or dismissed more than 7 days ago. Never touches
    an open task by construction -- deleted rows can't appear in any open-task query."""
    cutoff = now_utc - CLOSED_TASK_TTL
    result = await session.exec(
        select(Task).where(
            or_(
                and_(Task.status == TaskStatus.done, Task.completed_at < cutoff),
                and_(Task.status == TaskStatus.dismissed, Task.dismissed_at < cutoff),
            )
        )
    )
    tasks = list(result.all())
    for t in tasks:
        await session.delete(t)
    await session.commit()
    return len(tasks)


async def cleanup_old_thoughts(session: AsyncSession, now_utc: datetime) -> int:
    """Hard-deletes processed/error thoughts older than 14 days. Never touches pending
    thoughts (still-active work, or voice notes stuck pending forever -- out of scope
    for now). Relies on Task.thought_id's ON DELETE SET NULL: a surviving task just
    loses the link back to its original wording, it doesn't get deleted itself."""
    cutoff = now_utc - OLD_THOUGHT_TTL
    result = await session.exec(
        select(Thought).where(
            Thought.status.in_([ThoughtStatus.processed, ThoughtStatus.error]),
            Thought.created_at < cutoff,
        )
    )
    thoughts = list(result.all())
    for t in thoughts:
        await session.delete(t)
    await session.commit()
    return len(thoughts)
