from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CategoryKind = Literal["expense", "income", "transfer"]


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind
    parent_id: int | None = None
    icon: str | None = None
    color: str | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    kind: CategoryKind | None = None
    parent_id: int | None = None
    icon: str | None = None
    color: str | None = None


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str


class CategoryTreeNode(CategoryOut):
    children: list["CategoryTreeNode"] = []
