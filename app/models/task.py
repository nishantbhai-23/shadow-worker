import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Time
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models._types import BIGINT_PK


class TaskTier(str, enum.Enum):
    today = "today"
    week = "week"
    month = "month"
    someday = "someday"


class TaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    dismissed = "dismissed"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(default=None, sa_column=Column(BIGINT_PK, primary_key=True))
    user_id: int = Field(
        sa_column=Column(BigInteger(), ForeignKey("users.id"), nullable=False)
    )
    thought_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger(), ForeignKey("thoughts.id", ondelete="SET NULL"), nullable=True
        ),
    )
    title: str
    description: str | None = None
    domain: str | None = None  # unused in v0; reserved for pillar-1 specialization
    due_date: date | None = None
    due_time: time | None = Field(default=None, sa_column=Column(Time(), nullable=True))
    tier: TaskTier = Field(
        sa_column=Column(SAEnum(TaskTier, name="task_tier"), nullable=False)
    )
    status: TaskStatus = Field(
        sa_column=Column(
            SAEnum(TaskStatus, name="task_status"),
            nullable=False,
            default=TaskStatus.open,
        )
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    dismissed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    reminded_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
