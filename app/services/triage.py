import json
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, or_
from sqlmodel import select

from app.config import settings
from app.db import async_session_maker
from app.llm.factory import get_provider
from app.llm.prompts import build_triage_system_prompt
from app.models import Task, TaskStatus, TaskTier, Thought, ThoughtStatus, User
from app.services.tasks import mark_done, reopen, reschedule

_provider = None

OPEN_TASKS_LIMIT = 50
RECENTLY_CLOSED_WINDOW = timedelta(days=7)


def _get_provider():
    global _provider
    if _provider is None:
        _provider = get_provider(settings)
    return _provider


async def _open_tasks_context(session, user_id: int) -> list[dict]:
    result = await session.exec(
        select(Task)
        .where(Task.user_id == user_id, Task.status == TaskStatus.open)
        .order_by(Task.created_at.desc())
        .limit(OPEN_TASKS_LIMIT)
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in result.all()
    ]


async def _recently_closed_context(session, user_id: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - RECENTLY_CLOSED_WINDOW
    result = await session.exec(
        select(Task).where(
            Task.user_id == user_id,
            or_(
                and_(Task.status == TaskStatus.done, Task.completed_at >= cutoff),
                and_(Task.status == TaskStatus.dismissed, Task.dismissed_at >= cutoff),
            ),
        )
    )
    closed = []
    for t in result.all():
        closed_at = t.completed_at or t.dismissed_at
        closed.append({"id": t.id, "title": t.title, "closed_at": closed_at.isoformat()})
    return closed


async def process_thought(thought_id: int, bot=None) -> None:
    """Triage a single pending Thought: classify intent (new_task/mark_done/reschedule/
    reopen) and act on it. Self-contained: takes just an id, so it can be called from a
    poller today or a real queue consumer later without changing."""
    reply_text = None
    chat_id = None

    async with async_session_maker() as session:
        thought = await session.get(Thought, thought_id)
        if thought is None or thought.status != ThoughtStatus.pending:
            return

        user = await session.get(User, thought.user_id)
        chat_id = user.telegram_chat_id if user is not None else None

        open_tasks = await _open_tasks_context(session, thought.user_id)
        recently_closed = await _recently_closed_context(session, thought.user_id)

        provider = _get_provider()
        system_prompt = build_triage_system_prompt(
            date.today().isoformat(), settings.tz, open_tasks, recently_closed
        )
        try:
            raw_response = await provider.complete(system_prompt, thought.raw_text or "")
            payload = json.loads(raw_response)
            intent = payload.get("intent", "new_task")

            if intent == "new_task":
                for item in payload.get("tasks", []):
                    raw_due_date = item.get("due_date")
                    raw_due_time = item.get("due_time")
                    parsed_due_date = date.fromisoformat(raw_due_date) if raw_due_date else None
                    parsed_due_time = time.fromisoformat(raw_due_time) if raw_due_time else None
                    if parsed_due_time is not None and parsed_due_date is None:
                        # Defensive fallback: a due_time is meaningless without a date to
                        # anchor it to, and the reminder sweep requires both to be set.
                        # The prompt already instructs the model to do this itself, but
                        # don't rely on it -- a bare time almost always means today.
                        parsed_due_date = date.today()
                    session.add(
                        Task(
                            user_id=thought.user_id,
                            thought_id=thought.id,
                            title=item["title"],
                            due_date=parsed_due_date,
                            due_time=parsed_due_time,
                            tier=TaskTier(item.get("tier") or "someday"),
                        )
                    )
            elif intent == "mark_done":
                task = await mark_done(session, thought.user_id, payload.get("task_id"))
                if task is not None:
                    reply_text = (
                        f'Marked done: "{task.title}". Say "reopen it" to undo (within 7 days).'
                    )
            elif intent == "reschedule":
                raw_new_due_date = payload.get("new_due_date")
                task = await reschedule(
                    session,
                    thought.user_id,
                    payload.get("task_id"),
                    date.fromisoformat(raw_new_due_date) if raw_new_due_date else None,
                )
                if task is not None:
                    reply_text = f'Rescheduled "{task.title}" to {task.due_date.isoformat()}.'
            elif intent == "reopen":
                task = await reopen(session, thought.user_id, payload.get("task_id"))
                if task is not None:
                    reply_text = f'Reopened: "{task.title}".'

            thought.status = ThoughtStatus.processed
            thought.processed_at = datetime.now(timezone.utc)
        except Exception as exc:
            thought.status = ThoughtStatus.error
            thought.error_message = str(exc)[:2000]
            reply_text = None

        session.add(thought)
        await session.commit()

    if bot is not None and reply_text is not None and chat_id is not None:
        await bot.send_message(chat_id=chat_id, text=reply_text)


async def process_pending_thoughts(bot=None) -> None:
    """The worker: finds pending Thoughts with actual text and hands each id to
    process_thought(). This is the piece that gets swapped for a real queue consumer
    later. Voice thoughts stay pending (no raw_text yet) until a future transcription
    job fills in `transcript` — they're deliberately excluded here, not processed."""
    async with async_session_maker() as session:
        result = await session.exec(
            select(Thought.id).where(
                Thought.status == ThoughtStatus.pending,
                Thought.raw_text.is_not(None),
            )
        )
        pending_ids = result.all()

    for thought_id in pending_ids:
        await process_thought(thought_id, bot=bot)
