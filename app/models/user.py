from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime
from sqlmodel import Field, SQLModel

from app.models._types import BIGINT_PK


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, sa_column=Column(BIGINT_PK, primary_key=True))
    telegram_chat_id: int = Field(
        sa_column=Column(BigInteger(), unique=True, index=True, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
