"""Static checks on the SQLAlchemy column types themselves. SQLite (used by every other
test here) doesn't distinguish TIMESTAMP from TIMESTAMPTZ, or INTEGER from BIGINT, so a
type mismatch against real Postgres wouldn't be caught any other way in this suite --
both classes of bug have actually happened once already."""

from sqlalchemy import BigInteger, DateTime

from app.models import Task, Thought, User

DATETIME_COLUMNS = [
    (User, "created_at"),
    (Thought, "created_at"),
    (Thought, "processed_at"),
    (Task, "created_at"),
    (Task, "completed_at"),
]

BIGINT_COLUMNS = [
    (User, "id"),
    (User, "telegram_chat_id"),
    (Thought, "id"),
    (Thought, "user_id"),
    (Thought, "telegram_message_id"),
    (Task, "id"),
    (Task, "user_id"),
    (Task, "thought_id"),
]


def test_all_datetime_columns_are_timezone_aware():
    for model, column_name in DATETIME_COLUMNS:
        column_type = model.__table__.columns[column_name].type
        assert isinstance(column_type, DateTime), f"{model.__name__}.{column_name}"
        assert column_type.timezone is True, (
            f"{model.__name__}.{column_name} must be DateTime(timezone=True) "
            "to match the TIMESTAMPTZ columns in the Alembic migration"
        )


def test_all_id_and_telegram_id_columns_are_bigint():
    for model, column_name in BIGINT_COLUMNS:
        column_type = model.__table__.columns[column_name].type
        assert isinstance(column_type, BigInteger), (
            f"{model.__name__}.{column_name} must be BigInteger to match the BIGINT/"
            "BIGSERIAL columns in the Alembic migration -- a plain `int` field maps to "
            "a 32-bit INTEGER by default, which overflows on real Telegram chat ids"
        )
