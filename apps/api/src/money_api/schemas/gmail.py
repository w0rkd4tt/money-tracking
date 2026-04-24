from datetime import datetime

from pydantic import BaseModel


class GmailStatus(BaseModel):
    connected: bool
    account_email: str | None
    scopes: str | None
    expires_at: datetime | None
    last_sync_at: datetime | None
    last_history_id: str | None
    # True if connected scope allows modifying labels (mark as read)
    can_mark_read: bool = False


class GmailSyncResult(BaseModel):
    ok: bool
    processed: int
    ingested: int
    skipped: int
    errors: int
    marked_read: int = 0
    llm_fallback_used: int = 0
    history_id: str | None
    message: str


class IngestedEmailItem(BaseModel):
    """Email-sourced transaction enriched with LLM metadata for the
    email-ingest dashboard."""

    transaction_id: int
    ts: datetime
    amount: str
    currency: str
    status: str
    confidence: float
    account_id: int
    account_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    merchant: str | None = None
    note: str | None = None
    rule_name: str | None = None
    sender: str | None = None
    subject: str | None = None
    message_id: str | None = None
    is_llm_fallback: bool = False


class IngestStats(BaseModel):
    total: int
    by_rule: dict[str, int]
    by_status: dict[str, int]
    by_confidence: dict[str, int]
    llm_fallback_count: int
    rule_count: int
