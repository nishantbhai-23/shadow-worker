from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Task, TaskStatus, User

REMINDER_LEAD = timedelta(minutes=10)
STALE_WINDOW = timedelta(hours=24)


async def due_time_reminders(
    session: AsyncSession, now_utc: datetime, tz_name: str
) -> list[tuple[Task, int]]:
    """Finds tasks whose 10-minutes-before window has arrived and haven't been
    reminded yet, marks them reminded, and returns (task, telegram_chat_id) pairs
    for the caller to actually send. Commits the reminded_at update itself."""
    local_tz = ZoneInfo(tz_name)
    now_local = now_utc.astimezone(local_tz)

    result = await session.exec(
        select(Task, User.telegram_chat_id)
        .join(User, User.id == Task.user_id)
        .where(
            Task.status == TaskStatus.open,
            Task.due_date.is_not(None),
            Task.due_time.is_not(None),
            Task.reminded_at.is_(None),
        )
    )

    to_send: list[tuple[Task, int]] = []
    for task, chat_id in result.all():
        fire_at_local = datetime.combine(task.due_date, task.due_time, tzinfo=local_tz)
        reminder_at = fire_at_local - REMINDER_LEAD
        if reminder_at > now_local:
            continue  # window hasn't arrived yet

        task.reminded_at = now_utc  # mark regardless, even if stale, so it's never rechecked
        session.add(task)
        if now_local - reminder_at <= STALE_WINDOW:
            to_send.append((task, chat_id))
        # else: silently suppress -- the window is >24h stale (e.g. bot was down);
        # avoid sending a confusing "reminder" for a time long past.

    await session.commit()
    return to_send
