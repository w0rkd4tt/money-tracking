from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Category
from ..schemas.category import (
    CategoryCreate,
    CategoryOut,
    CategoryTreeNode,
    CategoryUpdate,
)
from ..schemas.dashboard import CategoryStatsOut
from ..services.dashboard import category_stats

router = APIRouter(prefix="/categories", tags=["categories"])


async def _recompute_path(session: AsyncSession, cat: Category) -> str:
    parts = [cat.name]
    parent_id = cat.parent_id
    while parent_id is not None:
        parent = await session.get(Category, parent_id)
        if not parent:
            break
        parts.append(parent.name)
        parent_id = parent.parent_id
    return " > ".join(reversed(parts))


@router.get("", response_model=list[CategoryOut])
async def list_categories(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Category).order_by(Category.path))).scalars().all()
    return rows


@router.get("/tree", response_model=list[CategoryTreeNode])
async def list_tree(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Category).order_by(Category.id))).scalars().all()
    node_map: dict[int, CategoryTreeNode] = {}
    roots: list[CategoryTreeNode] = []
    for r in rows:
        node_map[r.id] = CategoryTreeNode.model_validate(r)
    for r in rows:
        node = node_map[r.id]
        if r.parent_id and r.parent_id in node_map:
            node_map[r.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryCreate, session: AsyncSession = Depends(get_session)):
    # Reject duplicates — same (name, kind, parent_id) triple already exists.
    # A common accidental path: user clicks "+ Tạo" twice in the tree UI or the
    # LLM resolver creates a sibling when matching by name. Duplicates make
    # downstream category lookups ambiguous (resolver picks a random one),
    # skew dashboards (same spend appears twice in breakdowns), and break
    # the bucket mapping (1 category → 1 bucket rule).
    dup_q = select(Category.id).where(
        Category.name == data.name.strip(),
        Category.kind == data.kind,
    )
    if data.parent_id is None:
        dup_q = dup_q.where(Category.parent_id.is_(None))
    else:
        dup_q = dup_q.where(Category.parent_id == data.parent_id)
    existing_id = (await session.execute(dup_q.limit(1))).scalar_one_or_none()
    if existing_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"category '{data.name}' with the same kind + parent already "
                f"exists (id={existing_id}) — pick a different name or edit it"
            ),
        )

    cat = Category(**data.model_dump())
    cat.name = cat.name.strip()
    cat.path = cat.name
    session.add(cat)
    await session.flush()
    cat.path = await _recompute_path(session, cat)
    await session.commit()
    await session.refresh(cat)
    return cat


@router.get("/{category_id}", response_model=CategoryOut)
async def get_category(category_id: int, session: AsyncSession = Depends(get_session)):
    cat = await session.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "category not found")
    return cat


@router.get("/{category_id}/stats", response_model=CategoryStatsOut)
async def category_stats_endpoint(
    category_id: int,
    period: Literal["week", "month", "year"] = Query(default="month"),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await category_stats(session, category_id, period=period)
    except LookupError:
        raise HTTPException(404, "category not found")


@router.get("/stats/all", response_model=list[dict])
async def all_category_stats(
    period: Literal["week", "month", "year"] = Query(default="month"),
    kind: Literal["expense", "income", "transfer", "all"] = Query(default="all"),
    session: AsyncSession = Depends(get_session),
):
    """All categories with totals for the period, for /categories overview."""
    from datetime import date as _date

    from sqlalchemy import func as _func

    from ..models import Transaction
    from ..services.dashboard import period_range

    start, end, _ = period_range(period, _date.today())

    q = select(Category).order_by(Category.kind, Category.path)
    if kind != "all":
        q = q.where(Category.kind == kind)
    cats = (await session.execute(q)).scalars().all()

    sum_q = (
        select(
            Transaction.category_id,
            _func.coalesce(_func.sum(_func.abs(Transaction.amount)), 0).label("total"),
            _func.count(Transaction.id).label("cnt"),
        )
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
        )
        .group_by(Transaction.category_id)
    )
    rows = (await session.execute(sum_q)).all()
    agg = {r.category_id: (float(r.total or 0), int(r.cnt or 0)) for r in rows}

    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "path": c.path,
            "kind": c.kind,
            "icon": c.icon,
            "color": c.color,
            "total": agg.get(c.id, (0.0, 0))[0],
            "count": agg.get(c.id, (0.0, 0))[1],
        }
        for c in cats
    ]


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
):
    cat = await session.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "category not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    cat.path = await _recompute_path(session, cat)
    await session.commit()
    await session.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)):
    cat = await session.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "category not found")
    await session.delete(cat)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(409, f"cannot delete: {e}") from e
    return None
