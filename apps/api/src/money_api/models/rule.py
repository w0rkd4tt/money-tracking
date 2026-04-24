from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class Rule(Base):
    __tablename__ = "rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # gmail | chat | merchant_name
    pattern_type: Mapped[str] = mapped_column(String(20))  # regex | contains | sender_match
    pattern: Mapped[str] = mapped_column(String(500))
    extractor: Mapped[dict] = mapped_column(JSON, default=dict)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[int] = mapped_column(default=100)
    hit_count: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column(String(20), default="user")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
