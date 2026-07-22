"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Each enum is used in exactly one table below, so op.create_table/op.drop_table can
# manage its CREATE TYPE/DROP TYPE lifecycle implicitly -- no manual pre-creation needed.
content_type = sa.Enum("text", "voice", name="content_type")
thought_status = sa.Enum("pending", "processed", "error", name="thought_status")
task_tier = sa.Enum("today", "week", "month", "someday", name="task_tier")
task_status = sa.Enum("open", "done", "dismissed", name="task_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "thoughts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="telegram"),
        sa.Column("content_type", content_type, nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("telegram_file_id", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", thought_status, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thought_id", sa.BigInteger(), sa.ForeignKey("thoughts.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("tier", task_tier, nullable=False),
        sa.Column("status", task_status, nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("thoughts")
    op.drop_table("users")
