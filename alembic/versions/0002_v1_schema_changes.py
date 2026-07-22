"""v1 schema changes: due_time, reminded_at, dismissed_at, thought_id ON DELETE SET NULL

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("due_time", sa.Time(), nullable=True))
    op.add_column(
        "tasks", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tasks", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Without this, cleanup_old_thoughts (a future thought-retention job) would fail
    # outright the moment it tries to delete a Thought still referenced by a surviving
    # Task -- Postgres defaults an unnamed FK to ON DELETE RESTRICT/NO ACTION.
    op.drop_constraint("tasks_thought_id_fkey", "tasks", type_="foreignkey")
    op.create_foreign_key(
        "tasks_thought_id_fkey",
        "tasks",
        "thoughts",
        ["thought_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("tasks_thought_id_fkey", "tasks", type_="foreignkey")
    op.create_foreign_key(
        "tasks_thought_id_fkey", "tasks", "thoughts", ["thought_id"], ["id"]
    )

    op.drop_column("tasks", "reminded_at")
    op.drop_column("tasks", "dismissed_at")
    op.drop_column("tasks", "due_time")
