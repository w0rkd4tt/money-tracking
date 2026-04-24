from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PolicyAction = Literal["allow", "deny"]
PolicyPatternType = Literal["from", "to", "label", "subject", "query"]


class GmailPolicyBase(BaseModel):
    action: PolicyAction
    pattern_type: PolicyPatternType
    pattern: str = Field(min_length=1, max_length=500)
    priority: int = 100
    enabled: bool = True
    note: str | None = None


class GmailPolicyCreate(GmailPolicyBase):
    pass


class GmailPolicyOut(GmailPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class GmailPolicyTestRequest(BaseModel):
    query: str


class GmailPolicyTestResponse(BaseModel):
    allowed: bool
    rewritten_query: str | None
    matched_allows: list[int]
    matched_denies: list[int]
    reason: str


class LlmAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    session_id: int | None
    tool_name: str
    status: str
    duration_ms: int
    result_summary: str | None
    error: str | None
    trace_id: str | None


class LlmProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    timeout_sec: int = Field(default=120, ge=1, le=600)
    enabled: bool = True


class LlmProviderCreate(LlmProviderBase):
    api_key: str | None = None
    is_default: bool = False


class LlmProviderUpdate(BaseModel):
    endpoint: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_sec: int | None = Field(default=None, ge=1, le=600)
    api_key: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class LlmProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: Literal["builtin", "custom"]
    name: str
    endpoint: str
    model: str
    timeout_sec: int
    enabled: bool
    is_default: bool
    has_api_key: bool


class LlmProviderTestRequest(BaseModel):
    provider: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout_sec: int = Field(default=15, ge=1, le=120)


class LlmProviderTestResponse(BaseModel):
    ok: bool
    provider: str
    detail: str
