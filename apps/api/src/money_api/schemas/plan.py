from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlanStrategy = Literal["soft", "envelope", "zero_based", "pay_yourself_first"]
AllocMethod = Literal["amount", "percent"]
BucketStatus = Literal["ok", "warn", "over", "unplanned"]


class AllocationIn(BaseModel):
    bucket_id: int
    method: AllocMethod = "amount"
    value: Decimal = Field(ge=0)
    rollover: bool = True
    note: str | None = None


class AllocationOut(AllocationIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monthly_plan_id: int


class PlanBase(BaseModel):
    month: date  # any day of the target month; service will normalize to day 1
    expected_income: Decimal = Field(ge=0, default=Decimal("0"))
    strategy: PlanStrategy = "soft"
    carry_over_enabled: bool = True
    note: str | None = None


class PlanCreate(PlanBase):
    allocations: list[AllocationIn] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    expected_income: Decimal | None = Field(default=None, ge=0)
    strategy: PlanStrategy | None = None
    carry_over_enabled: bool | None = None
    note: str | None = None
    allocations: list[AllocationIn] | None = None  # if provided, replaces all allocations


class PlanOut(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    allocations: list[AllocationOut] = Field(default_factory=list)


class BucketStatusOut(BaseModel):
    bucket_id: int
    bucket_name: str
    method: AllocMethod
    value: Decimal  # raw config (amount or percent)
    allocated: Decimal  # computed VND allocated (after applying percent × income)
    spent: Decimal
    carry_in: Decimal  # rollover from previous month (+ dư / − vượt)
    remaining: Decimal  # allocated + carry_in − spent
    pct: float  # spent / (allocated + carry_in) × 100, clamped when denom ≤ 0
    status: BucketStatus
    rollover: bool


class PlanSummaryOut(BaseModel):
    month: date
    strategy: PlanStrategy
    expected_income: Decimal
    actual_income: Decimal
    total_allocated: Decimal
    total_spent: Decimal
    unplanned_spent: Decimal  # spent in categories that don't belong to any bucket
    buckets: list[BucketStatusOut]


class IncomeSuggestOut(BaseModel):
    month: date
    suggested: Decimal
    samples: list[dict]  # [{month: 2026-03-01, income: 30000000}, ...]
    method: Literal["avg_3m", "fallback"]
