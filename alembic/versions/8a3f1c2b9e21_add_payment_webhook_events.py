"""add payment webhook events

Revision ID: 8a3f1c2b9e21
Revises: 25900b233474
Create Date: 2026-06-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a3f1c2b9e21"
down_revision: Union[str, None] = "25900b233474"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("result", sa.String(length=50), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payment_webhook_events_provider_event_id"),
            ["provider_event_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_payment_webhook_events_order_id"),
            ["order_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_order_id"))
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_provider_event_id"))
    op.drop_table("payment_webhook_events")
