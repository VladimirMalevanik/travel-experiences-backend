"""add moderation decisions, complaints, audit logs and related fields

Revision ID: c7d2e9f4a1b8
Revises: 8a3f1c2b9e21
Create Date: 2026-06-12 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d2e9f4a1b8"
down_revision: Union[str, None] = "8a3f1c2b9e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- experiences: moderation reason fields ---
    with op.batch_alter_table("experiences", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("moderation_reason_code", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("moderation_reason_text", sa.Text(), nullable=True)
        )

    # --- analytics_events: event_version + occurred_at ---
    with op.batch_alter_table("analytics_events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "event_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)
        )

    # --- moderation_decisions ---
    op.create_table(
        "moderation_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experience_id", sa.Integer(), nullable=False),
        sa.Column("moderator_id", sa.Integer(), nullable=True),
        sa.Column(
            "decision",
            sa.Enum("publish", "reject", name="moderation_decision_type"),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["experience_id"], ["experiences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("moderation_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_moderation_decisions_experience_id"),
            ["experience_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_moderation_decisions_moderator_id"),
            ["moderator_id"],
            unique=False,
        )

    # --- complaints ---
    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_user_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "resolved", "rejected", name="complaint_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderator_id", sa.Integer(), nullable=True),
        sa.Column("resolution_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("complaints", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_complaints_reporter_user_id"),
            ["reporter_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_complaints_target_id"), ["target_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_complaints_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_complaints_moderator_id"), ["moderator_id"], unique=False
        )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_logs_actor_user_id"), ["actor_user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_logs_action"), ["action"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_logs_created_at"), ["created_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_created_at"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_action"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_actor_user_id"))
    op.drop_table("audit_logs")

    with op.batch_alter_table("complaints", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_complaints_moderator_id"))
        batch_op.drop_index(batch_op.f("ix_complaints_status"))
        batch_op.drop_index(batch_op.f("ix_complaints_target_id"))
        batch_op.drop_index(batch_op.f("ix_complaints_reporter_user_id"))
    op.drop_table("complaints")

    with op.batch_alter_table("moderation_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_moderation_decisions_moderator_id"))
        batch_op.drop_index(batch_op.f("ix_moderation_decisions_experience_id"))
    op.drop_table("moderation_decisions")

    with op.batch_alter_table("analytics_events", schema=None) as batch_op:
        batch_op.drop_column("occurred_at")
        batch_op.drop_column("event_version")

    with op.batch_alter_table("experiences", schema=None) as batch_op:
        batch_op.drop_column("moderation_reason_text")
        batch_op.drop_column("moderation_reason_code")
