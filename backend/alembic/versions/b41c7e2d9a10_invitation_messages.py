"""invitation messages: вопросы по приглашению до раскрытия контактов

Revision ID: b41c7e2d9a10
Revises: 9087cdd34ed1
Create Date: 2026-10-20 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models  # кастомный тип UTCDateTime


revision: str = "b41c7e2d9a10"
down_revision: Union[str, Sequence[str], None] = "9087cdd34ed1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invitation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invitation_id", sa.Integer(), nullable=False),
        sa.Column("author_role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", app.models.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invitation_messages_invitation_id"), "invitation_messages", ["invitation_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invitation_messages_invitation_id"), table_name="invitation_messages")
    op.drop_table("invitation_messages")
