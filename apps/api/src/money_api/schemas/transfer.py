from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TransferCreate(BaseModel):
    ts: datetime
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0)
    fee: Decimal = Decimal("0")
    currency: str = "VND"
    fx_rate: Decimal | None = None
    note: str | None = None


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    from_account_id: int
    to_account_id: int
    amount: Decimal
    fee: Decimal
    currency: str
    fx_rate: Decimal | None
    note: str | None
    source: str
    created_at: datetime
    transaction_ids: list[int] = []
