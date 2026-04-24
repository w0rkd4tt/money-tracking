from pydantic import BaseModel, ConfigDict


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_account_id: int | None
    locale: str
    timezone: str
    default_currency: str
    llm_allow_cloud: bool
    llm_agent_enabled: bool
    llm_gmail_tool_enabled: bool
    theme: str


class SettingsUpdate(BaseModel):
    default_account_id: int | None = None
    locale: str | None = None
    timezone: str | None = None
    default_currency: str | None = None
    llm_allow_cloud: bool | None = None
    llm_agent_enabled: bool | None = None
    llm_gmail_tool_enabled: bool | None = None
    theme: str | None = None
