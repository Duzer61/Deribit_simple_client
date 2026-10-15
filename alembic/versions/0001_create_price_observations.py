"""create price observations

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "ticker IN ('btc_usd', 'eth_usd')",
            name="ck_price_observations_ticker",
        ),
        sa.CheckConstraint("price > 0", name="ck_price_observations_price_positive"),
        sa.CheckConstraint(
            "timestamp >= 0",
            name="ck_price_observations_timestamp_non_negative",
        ),
    )
    op.create_index(
        "ix_price_observations_ticker_timestamp_id",
        "price_observations",
        ["ticker", "timestamp", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_price_observations_ticker_timestamp_id",
        table_name="price_observations",
    )
    op.drop_table("price_observations")
