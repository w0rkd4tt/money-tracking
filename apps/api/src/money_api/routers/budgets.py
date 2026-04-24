from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Budget
from ..schemas.budget import BudgetCreate, BudgetOut, BudgetStatusOut, BudgetUpdate
from ..services.budgets import statuses

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
async def list_budgets(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Budget))).scalars().all()
    return rows


@router.post("", response_model=BudgetOut, status_code=201)
async def create_budget(data: BudgetCreate, session: AsyncSession = Depends(get_session)):
    b = Budget(**data.model_dump())
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


@router.get("/status", response_model=list[BudgetStatusOut])
async def budget_status(session: AsyncSession = Depends(get_session)):
    return await statuses(session)


@router.patch("/{budget_id}", response_model=BudgetOut)
async def update_budget(
    budget_id: int, data: BudgetUpdate, session: AsyncSession = Depends(get_session)
):
    b = await session.get(Budget, budget_id)
    if not b:
        raise HTTPException(404, "budget not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    await session.commit()
    await session.refresh(b)
    return b


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(budget_id: int, session: AsyncSession = Depends(get_session)):
    b = await session.get(Budget, budget_id)
    if not b:
        raise HTTPException(404, "budget not found")
    await session.delete(b)
    await session.commit()
    return None
