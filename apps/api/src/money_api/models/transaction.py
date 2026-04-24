from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        Index("ix_tx_account_ts", "account_id", "ts"),
        Index("ix_tx_category_ts", "category_id", "ts"),
        Index("ix_tx_status_ts", "status", "ts"),
        UniqueConstraint("source", "raw_ref", name="uq_tx_source_raw_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="RESTRICT"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant.id", ondelete="SET NULL"), nullable=True
    )
    merchant_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    raw_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    llm_tags: Mapped[dict] = mapped_column(JSON, default=dict)
    transfer_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("transfer_group.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
