from app.models import ContentType, ThoughtStatus
from app.services.capture import (
    capture_text,
    capture_voice,
    get_allowed_user,
    get_or_create_user,
)


async def test_get_or_create_user_is_idempotent(session):
    first = await get_or_create_user(session, telegram_chat_id=42)
    second = await get_or_create_user(session, telegram_chat_id=42)
    assert first.id == second.id


async def test_get_allowed_user_returns_none_when_unclaimed(session):
    assert await get_allowed_user(session) is None


async def test_get_allowed_user_returns_the_single_claimed_user(session):
    user = await get_or_create_user(session, telegram_chat_id=42)
    allowed = await get_allowed_user(session)
    assert allowed.id == user.id


async def test_capture_text_creates_pending_thought(session):
    user = await get_or_create_user(session, telegram_chat_id=1)
    thought = await capture_text(session, user_id=user.id, raw_text="buy milk", telegram_message_id=99)

    assert thought.content_type == ContentType.text
    assert thought.status == ThoughtStatus.pending
    assert thought.raw_text == "buy milk"
    assert thought.telegram_message_id == 99


async def test_capture_voice_has_no_raw_text_and_stores_file_id(session):
    user = await get_or_create_user(session, telegram_chat_id=1)
    thought = await capture_voice(
        session, user_id=user.id, telegram_file_id="file123", telegram_message_id=5
    )

    assert thought.content_type == ContentType.voice
    assert thought.status == ThoughtStatus.pending
    assert thought.raw_text is None
    assert thought.telegram_file_id == "file123"
