from datetime import date, datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Task, TaskStatus


async def mark_done(session: AsyncSession, user_id: int, task_id: int | None) -> Task | None:
    if task_id is None:
        return None
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id or task.status != TaskStatus.open:
        return None
    task.status = TaskStatus.done
    task.completed_at = datetime.now(timezone.utc)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def reopen(session: AsyncSession, user_id: int, task_id: int | None) -> Task | None:
    if task_id is None:
        return None
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id or task.status not in (
        TaskStatus.done,
        TaskStatus.dismissed,
    ):
        return None
    task.status = TaskStatus.open
    task.completed_at = None
    task.dismissed_at = None
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def reschedule(
    session: AsyncSession, user_id: int, task_id: int | None, new_due_date: date | None
) -> Task | None:
    if task_id is None or new_due_date is None:
        return None
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id or task.status != TaskStatus.open:
        return None
    task.due_date = new_due_date
    task.reminded_at = None  # give it a fresh reminder window if due_time is still set
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def rollover_backlog(session: AsyncSession, user_id: int) -> int:
    today = date.today()
    result = await session.exec(
        select(Task).where(
            Task.user_id == user_id,
            Task.status == TaskStatus.open,
            Task.due_date.is_not(None),
            Task.due_date < today,
        )
    )
    tasks = list(result.all())
    for t in tasks:
        t.due_date = t.due_date + timedelta(days=7)
        t.reminded_at = None
    session.add_all(tasks)
    await session.commit()
    return len(tasks)


async def clear_all_open_tasks(session: AsyncSession, user_id: int) -> int:
    result = await session.exec(
        select(Task).where(Task.user_id == user_id, Task.status == TaskStatus.open)
    )
    tasks = list(result.all())
    now = datetime.now(timezone.utc)
    for t in tasks:
        t.status = TaskStatus.dismissed
        t.dismissed_at = now
    session.add_all(tasks)
    await session.commit()
    return len(tasks)
