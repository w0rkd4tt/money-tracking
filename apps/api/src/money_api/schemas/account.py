from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccountType = Literal["cash", "bank", "ewallet", "credit", "saving", "investment"]


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    currency: str = Field(default="VND", min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")
    icon: str | None = None
    color: str | None = None
    is_default: bool = False
    credit_limit: Decimal | None = None
    statement_close_day: int | None = Field(default=None, ge=1, le=31)


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = None
    type: AccountType | None = None
    currency: str | None = None
    opening_balance: Decimal | None = None
    icon: str | None = None
    color: str | None = None
    archived: bool | None = None
    is_default: bool | None = None
    credit_limit: Decimal | None = None
    statement_close_day: int | None = Field(default=None, ge=1, le=31)


class AccountOut(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    archived: bool


class BalanceOut(BaseModel):
    account_id: int
    name: str
    type: AccountType
    currency: str
    balance: Decimal
    # Credit card: debt = |balance| when balance < 0.
    credit_limit: Decimal | None = None
    debt: Decimal | None = None
    available_credit: Decimal | None = None
    utilization_pct: float | None = None
