from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class NotifyLog(Base):
    """Dedup notifications: only send one per event_key within its period."""

    __tablename__ = "notify_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))  # telegram | email
    event_key: Mapped[str] = mapped_column(String(200), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
