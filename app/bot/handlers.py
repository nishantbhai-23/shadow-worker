from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.db import async_session_maker
from app.models import User
from app.services.capture import (
    capture_text,
    capture_voice,
    get_allowed_user,
    get_or_create_user,
)
from app.services.digest import get_backlog, get_completed, get_digest
from app.services.tasks import clear_all_open_tasks, rollover_backlog


def require_allowed_user(handler):
    """Rejects (silently) any chat that isn't the one claimed via /start. Not real
    auth — just the cheap gate described in the plan. The wrapper is what PTB calls
    (update, context); it looks up the allowed user once and passes it into the real
    handler, which callers never invoke directly."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with async_session_maker() as session:
            user = await get_allowed_user(session)
        if user is None or user.telegram_chat_id != update.effective_chat.id:
            return
        await handler(update, context, user)

    return wrapper


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    async with async_session_maker() as session:
        existing = await get_allowed_user(session)

        if existing is None:
            provided = context.args[0] if context.args else None
            if provided != settings.telegram_start_secret:
                # Never hint whether the token was close or wrong.
                await update.message.reply_text("Unknown command.")
                return
            await get_or_create_user(session, chat_id)
        elif existing.telegram_chat_id != chat_id:
            return  # already claimed by someone else — stay silent

    await update.message.reply_text(
        "Shadow Worker is alive. Send me a thought and I'll capture it."
    )


@require_allowed_user
async def capture_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user: User
) -> None:
    async with async_session_maker() as session:
        await capture_text(
            session,
            user_id=user.id,
            raw_text=update.message.text,
            telegram_message_id=update.message.message_id,
        )
    await update.message.reply_text("Captured.")


@require_allowed_user
async def capture_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user: User
) -> None:
    async with async_session_maker() as session:
        await capture_voice(
            session,
            user_id=user.id,
            telegram_file_id=update.message.voice.file_id,
            telegram_message_id=update.message.message_id,
        )
    await update.message.reply_text(
        "Got the voice note — transcription isn't wired up yet."
    )


async def _reply_digest(update: Update, user: User, bucket: str) -> None:
    async with async_session_maker() as session:
        text = await get_digest(session, user.id, bucket)
    await update.message.reply_text(text)


@require_allowed_user
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    await _reply_digest(update, user, "today")


@require_allowed_user
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    await _reply_digest(update, user, "week")


@require_allowed_user
async def month(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    await _reply_digest(update, user, "month")


@require_allowed_user
async def someday(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    await _reply_digest(update, user, "someday")


@require_allowed_user
async def now(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    await _reply_digest(update, user, "now")


@require_allowed_user
async def completed(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    async with async_session_maker() as session:
        text = await get_completed(session, user.id)
    await update.message.reply_text(text)


@require_allowed_user
async def backlog(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    async with async_session_maker() as session:
        text = await get_backlog(session, user.id)
    await update.message.reply_text(text)


@require_allowed_user
async def rollover(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    async with async_session_maker() as session:
        count = await rollover_backlog(session, user.id)
    await update.message.reply_text(f"Rolled {count} backlog task(s) forward by a week.")


@require_allowed_user
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    async with async_session_maker() as session:
        count = await clear_all_open_tasks(session, user.id)
    await update.message.reply_text(
        f"Cleared {count} task(s). They'll be permanently removed in 7 days -- "
        f'say "reopen the [task] thing" before then if you change your mind.'
    )
