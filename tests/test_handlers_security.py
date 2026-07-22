from unittest.mock import AsyncMock, MagicMock

import pytest

import app.bot.handlers as handlers_module
from app.services.capture import get_allowed_user


def make_update(chat_id, args=None, text=None, message_id=1):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    update.message.text = text
    update.message.message_id = message_id
    context = MagicMock()
    context.args = args or []
    return update, context


async def test_start_claims_bot_with_correct_secret(session, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    update, context = make_update(chat_id=100, args=["test-secret"])  # matches conftest's TELEGRAM_START_SECRET

    await handlers_module.start(update, context)

    reply_text = update.message.reply_text.await_args.args[0]
    assert "alive" in reply_text.lower()

    allowed = await get_allowed_user(session)
    assert allowed is not None
    assert allowed.telegram_chat_id == 100


async def test_start_rejects_wrong_secret(session, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    update, context = make_update(chat_id=100, args=["wrong-secret"])

    await handlers_module.start(update, context)

    assert update.message.reply_text.await_args.args[0] == "Unknown command."
    assert await get_allowed_user(session) is None


async def test_start_rejects_missing_secret(session, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    update, context = make_update(chat_id=100, args=[])

    await handlers_module.start(update, context)

    assert update.message.reply_text.await_args.args[0] == "Unknown command."
    assert await get_allowed_user(session) is None


async def test_start_from_different_chat_after_claim_is_silently_ignored(session, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    claim_update, claim_context = make_update(chat_id=100, args=["test-secret"])
    await handlers_module.start(claim_update, claim_context)

    other_update, other_context = make_update(chat_id=200, args=["test-secret"])
    await handlers_module.start(other_update, other_context)

    other_update.message.reply_text.assert_not_awaited()
    allowed = await get_allowed_user(session)
    assert allowed.telegram_chat_id == 100  # unchanged


async def test_require_allowed_user_blocks_unclaimed_chat(session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    update, context = make_update(chat_id=999, text="a rambling thought")

    await handlers_module.capture_text_message(update, context)

    update.message.reply_text.assert_not_awaited()


async def test_require_allowed_user_blocks_different_chat_after_claim(session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    claim_update, claim_context = make_update(chat_id=100, args=["test-secret"])
    await handlers_module.start(claim_update, claim_context)

    update, context = make_update(chat_id=999, text="a rambling thought")
    await handlers_module.capture_text_message(update, context)

    update.message.reply_text.assert_not_awaited()


async def test_require_allowed_user_allows_claimed_chat(session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    claim_update, claim_context = make_update(chat_id=100, args=["test-secret"])
    await handlers_module.start(claim_update, claim_context)

    update, context = make_update(chat_id=100, text="a rambling thought")
    await handlers_module.capture_text_message(update, context)

    update.message.reply_text.assert_awaited_once_with("Captured.")


NEW_COMMAND_HANDLERS = [
    handlers_module.completed,
    handlers_module.backlog,
    handlers_module.rollover,
    handlers_module.clear,
]


@pytest.mark.parametrize("handler", NEW_COMMAND_HANDLERS)
async def test_new_commands_blocked_for_unclaimed_chat(handler, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    update, context = make_update(chat_id=999)

    await handler(update, context)

    update.message.reply_text.assert_not_awaited()


@pytest.mark.parametrize("handler", NEW_COMMAND_HANDLERS)
async def test_new_commands_reply_for_claimed_chat(handler, session_maker, monkeypatch):
    monkeypatch.setattr(handlers_module, "async_session_maker", session_maker)
    claim_update, claim_context = make_update(chat_id=100, args=["test-secret"])
    await handlers_module.start(claim_update, claim_context)

    update, context = make_update(chat_id=100)
    await handler(update, context)

    update.message.reply_text.assert_awaited_once()
