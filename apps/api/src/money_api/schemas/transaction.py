from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TransactionStatus = Literal["pending", "confirmed", "rejected"]
# Free-form string so seeds / future integrations (seed_demo, sms_forward, bank_csv)
# are accepted without a schema migration. Known values listed for reference.
TransactionSource = str
KNOWN_TRANSACTION_SOURCES = (
    "manual",
    "chat_web",
    "chat_telegram",
    "gmail",
    "sms",
    "import_csv",
    "agent_propose",
    "seed_demo",
)


class TransactionBase(BaseModel):
    ts: datetime
    amount: Decimal
    currency: str = "VND"
    account_id: int
    category_id: int | None = None
    merchant_id: int | None = None
    merchant_text: str | None = None
    note: str | None = Field(default=None, max_length=500)
    source: TransactionSource = "manual"
    raw_ref: str | None = None
    confidence: float = 1.0
    status: TransactionStatus = "confirmed"


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    ts: datetime | None = None
    amount: Decimal | None = None
    account_id: int | None = None
    category_id: int | None = None
    merchant_id: int | None = None
    merchant_text: str | None = None
    note: str | None = None
    status: TransactionStatus | None = None


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_group_id: int | None = None
    created_at: datetime
    updated_at: datetime


class TransactionStats(BaseModel):
    total_expense: Decimal
    total_income: Decimal
    net: Decimal
    count: int
