"""coupons and redemptions

Revision ID: a1b2c3d4e5f6
Revises: 53dfb300d441
Create Date: 2026-09-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "53dfb300d441"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="days"),
        sa.Column("value_days", sa.Integer(), server_default="0"),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("redeemed_count", sa.Integer(), server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"], unique=True)
    op.create_table(
        "coupon_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coupon_id", sa.Integer(), sa.ForeignKey("coupons.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("tg_id", sa.Integer(), nullable=False),
        sa.Column("days_granted", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_coupon_redemptions_coupon_id", "coupon_redemptions", ["coupon_id"])
    op.create_index("ix_coupon_redemptions_tenant_id", "coupon_redemptions", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("coupon_redemptions")
    op.drop_table("coupons")
