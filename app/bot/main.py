import datetime as dt
import logging
from zoneinfo import ZoneInfo

from sqlmodel import select
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.handlers import (
    backlog,
    capture_text_message,
    capture_voice_message,
    clear,
    completed,
    month,
    now,
    rollover,
    someday,
    start,
    today,
    week,
)
from app.config import settings
from app.db import async_session_maker
from app.models import User
from app.services.cleanup import cleanup_closed_tasks, cleanup_old_thoughts
from app.services.digest import get_due_today
from app.services.reminders import due_time_reminders
from app.services.triage import process_pending_thoughts


logger = logging.getLogger(__name__)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text(
            "Something went wrong on my end handling that -- it's logged, not silently lost."
        )


async def _triage_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await process_pending_thoughts(bot=context.bot)


async def _daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    async with async_session_maker() as session:
        result = await session.exec(select(User))
        digests = [
            (user.telegram_chat_id, await get_due_today(session, user.id))
            for user in result.all()
        ]

    for chat_id, text in digests:
        await context.bot.send_message(chat_id=chat_id, text=f"Today:\n{text}")


async def _time_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    async with async_session_maker() as session:
        to_send = await due_time_reminders(session, dt.datetime.now(dt.timezone.utc), settings.tz)

    for task, chat_id in to_send:
        due_str = task.due_time.strftime("%H:%M")
        await context.bot.send_message(
            chat_id=chat_id, text=f'Reminder in 10 min: "{task.title}" at {due_str}.'
        )


async def _cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    now_utc = dt.datetime.now(dt.timezone.utc)
    async with async_session_maker() as session:
        await cleanup_closed_tasks(session, now_utc)
    async with async_session_maker() as session:
        await cleanup_old_thoughts(session, now_utc)


def build_application() -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_error_handler(_on_error)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("week", week))
    application.add_handler(CommandHandler("month", month))
    application.add_handler(CommandHandler("someday", someday))
    application.add_handler(CommandHandler("now", now))
    application.add_handler(CommandHandler("completed", completed))
    application.add_handler(CommandHandler("backlog", backlog))
    application.add_handler(CommandHandler("rollover", rollover))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, capture_text_message)
    )
    application.add_handler(MessageHandler(filters.VOICE, capture_voice_message))
    application.job_queue.run_repeating(_triage_job, interval=5, first=5)
    application.job_queue.run_repeating(_time_reminder_job, interval=60, first=30, name="time_reminders")
    application.job_queue.run_repeating(_cleanup_job, interval=3600, first=120, name="cleanup")
    application.job_queue.run_daily(
        _daily_digest_job,
        time=dt.time(hour=settings.digest_hour, tzinfo=ZoneInfo(settings.tz)),
        name="daily_digest",
    )
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
