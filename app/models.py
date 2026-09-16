from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    bot_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="trial")
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    identity: Mapped[Identity | None] = relationship(back_populates="tenant", uselist=False)


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    official_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    alert_text: Mapped[str] = mapped_column(String(200), default="")
    card_text: Mapped[str] = mapped_column(Text, default="")

    tenant: Mapped[Tenant] = relationship(back_populates="identity")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("telegram_charge_id", name="uq_charge"),
        UniqueConstraint("txid", name="uq_txid"),
        UniqueConstraint("public_code", name="uq_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_code: Mapped[str] = mapped_column(String(16), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    rail: Mapped[str] = mapped_column(String(10))
    plan: Mapped[str] = mapped_column(String(20))
    period_days: Mapped[int]
    amount: Mapped[float] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    chain: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pay_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pay_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payload: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    txid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
