import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models._types import BIGINT_PK


class ContentType(str, enum.Enum):
    text = "text"
    voice = "voice"


class ThoughtStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    error = "error"


class Thought(SQLModel, table=True):
    __tablename__ = "thoughts"

    id: int | None = Field(default=None, sa_column=Column(BIGINT_PK, primary_key=True))
    user_id: int = Field(
        sa_column=Column(BigInteger(), ForeignKey("users.id"), nullable=False)
    )
    source: str = Field(default="telegram")
    content_type: ContentType = Field(
        sa_column=Column(SAEnum(ContentType, name="content_type"), nullable=False)
    )
    raw_text: str | None = None
    telegram_file_id: str | None = None
    transcript: str | None = None
    telegram_message_id: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    status: ThoughtStatus = Field(
        sa_column=Column(
            SAEnum(ThoughtStatus, name="thought_status"),
            nullable=False,
            default=ThoughtStatus.pending,
        )
    )
    error_message: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    processed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
