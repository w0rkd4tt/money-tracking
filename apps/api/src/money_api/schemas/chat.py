from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChatIntent = Literal["create_transaction", "create_transfer", "query", "unknown"]


class ExtractedTransaction(BaseModel):
    id: int | None = None
    status: str = "pending"
    amount: int
    currency: str = "VND"
    kind: Literal["expense", "income", "transfer"] = "expense"
    account: str
    to_account: str | None = None
    category: str | None = None
    merchant: str | None = None
    ts: datetime
    note: str | None = None
    confidence: float = 0.0
    ambiguous_fields: list[str] = []


class ChatMessageRequest(BaseModel):
    channel: Literal["web", "telegram"] = "web"
    external_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    provider: str | None = Field(default=None, min_length=1, max_length=100)


class ChatMessageResponse(BaseModel):
    intent: ChatIntent
    transactions: list[ExtractedTransaction] = []
    reply_text: str
    follow_up_questions: list[str] = []
    fallback_used: bool = False
    # Name of the provider that actually handled this turn. Required — every
    # code path must resolve and pass it (no misleading default).
    provider: str
