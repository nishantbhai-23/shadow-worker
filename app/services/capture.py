from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ContentType, Thought, ThoughtStatus, User


async def get_or_create_user(session: AsyncSession, telegram_chat_id: int) -> User:
    result = await session.exec(select(User).where(User.telegram_chat_id == telegram_chat_id))
    user = result.first()
    if user is not None:
        return user

    user = User(telegram_chat_id=telegram_chat_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_allowed_user(session: AsyncSession) -> User | None:
    """v0 is single-user: the one row in `users` (if claimed) *is* the allowlist."""
    result = await session.exec(select(User))
    return result.first()


async def capture_text(
    session: AsyncSession,
    user_id: int,
    raw_text: str,
    telegram_message_id: int | None,
) -> Thought:
    thought = Thought(
        user_id=user_id,
        content_type=ContentType.text,
        raw_text=raw_text,
        telegram_message_id=telegram_message_id,
        status=ThoughtStatus.pending,
    )
    session.add(thought)
    await session.commit()
    await session.refresh(thought)
    return thought


async def capture_voice(
    session: AsyncSession,
    user_id: int,
    telegram_file_id: str,
    telegram_message_id: int | None,
) -> Thought:
    """Stores the voice note's file_id only. Stays status=pending indefinitely (no
    raw_text) until a future transcription job fills in `transcript` and lets it flow
    into the same triage path as text — the worker query only picks up thoughts that
    already have text, so this never enters triage as-is."""
    thought = Thought(
        user_id=user_id,
        content_type=ContentType.voice,
        telegram_file_id=telegram_file_id,
        telegram_message_id=telegram_message_id,
        status=ThoughtStatus.pending,
    )
    session.add(thought)
    await session.commit()
    await session.refresh(thought)
    return thought
