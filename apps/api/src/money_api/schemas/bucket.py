from pydantic import BaseModel, ConfigDict, Field


class BucketBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str | None = None
    color: str | None = None
    sort_order: int = 0
    note: str | None = None


class BucketCreate(BucketBase):
    category_ids: list[int] = Field(default_factory=list)
    account_ids: list[int] = Field(default_factory=list)


class BucketUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None
    archived: bool | None = None
    note: str | None = None
    category_ids: list[int] | None = None  # if provided, replaces mapping
    account_ids: list[int] | None = None  # if provided, replaces mapping


class BucketOut(BucketBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    archived: bool
    category_ids: list[int] = Field(default_factory=list)
    account_ids: list[int] = Field(default_factory=list)
