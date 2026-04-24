from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BudgetPeriod = Literal["monthly", "weekly"]


class BudgetBase(BaseModel):
    category_id: int | None = None
    period: BudgetPeriod = "monthly"
    period_start: date
    limit_amount: Decimal = Field(gt=0)
    rollover: bool = False


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    limit_amount: Decimal | None = None
    rollover: bool | None = None


class BudgetOut(BudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class BudgetStatusOut(BaseModel):
    budget_id: int
    category_id: int | None
    category_name: str | None
    period: str
    period_start: date
    limit_amount: Decimal
    spent: Decimal
    remaining: Decimal
    pct: float
    status: Literal["ok", "warn", "over"]
