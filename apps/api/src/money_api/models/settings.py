from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AppSetting(Base):
    """Singleton row (id=1) lưu user preferences."""

    __tablename__ = "app_setting"

    id: Mapped[int] = mapped_column(primary_key=True)
    default_account_id: Mapped[int | None] = mapped_column(nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="vi-VN")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Ho_Chi_Minh")
    default_currency: Mapped[str] = mapped_column(String(3), default="VND")
    llm_allow_cloud: Mapped[bool] = mapped_column(default=False)
    llm_agent_enabled: Mapped[bool] = mapped_column(default=True)
    llm_gmail_tool_enabled: Mapped[bool] = mapped_column(default=False)
    theme: Mapped[str] = mapped_column(String(20), default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
