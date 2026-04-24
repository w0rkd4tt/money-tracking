from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..schemas.dashboard import CashflowPoint, DashboardOverview
from ..services.dashboard import last_n_days, overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Period = Literal["week", "month", "year"]


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    period: Period = Query(default="month"),
    session: AsyncSession = Depends(get_session),
):
    return await overview(session, period=period)


@router.get("/cashflow", response_model=list[CashflowPoint])
async def dashboard_cashflow(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await last_n_days(session, days=days)
