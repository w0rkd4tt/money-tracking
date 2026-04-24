from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MonthlyPlan(Base):
    __tablename__ = "monthly_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[date] = mapped_column(Date, unique=True)  # first day of the month
    expected_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    # soft | envelope | zero_based | pay_yourself_first
    strategy: Mapped[str] = mapped_column(String(20), default="soft")
    carry_over_enabled: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PlanAllocation(Base):
    __tablename__ = "plan_allocation"
    __table_args__ = (
        UniqueConstraint("monthly_plan_id", "bucket_id", name="uq_plan_bucket"),
        Index("ix_plan_alloc_plan", "monthly_plan_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    monthly_plan_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_plan.id", ondelete="CASCADE")
    )
    bucket_id: Mapped[int] = mapped_column(
        ForeignKey("allocation_bucket.id", ondelete="RESTRICT")
    )
    method: Mapped[str] = mapped_column(String(10), default="amount")  # amount | percent
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    rollover: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
