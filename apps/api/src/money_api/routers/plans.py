from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import AllocationBucket, MonthlyPlan, PlanAllocation
from ..schemas.plan import (
    AllocationOut,
    IncomeSuggestOut,
    PlanCreate,
    PlanOut,
    PlanSummaryOut,
    PlanUpdate,
)
from ..services.plans import (
    clone_plan,
    create_plan_with_allocs,
    get_allocations,
    get_plan_by_month,
    month_start,
    plan_summary,
    replace_allocations,
    suggest_income,
)

router = APIRouter(prefix="/plans", tags=["plans"])


def _parse_month(month: str) -> date:
    """Accept 'YYYY-MM' or 'YYYY-MM-DD'. Normalize to day 1."""
    try:
        if len(month) == 7:
            y, m = month.split("-")
            return date(int(y), int(m), 1)
        return month_start(date.fromisoformat(month))
    except Exception as e:
        raise HTTPException(400, f"invalid month '{month}', expected YYYY-MM") from e


async def _validate_allocations(session: AsyncSession, allocations: list) -> None:
    if not allocations:
        return
    bucket_ids = [a.bucket_id for a in allocations]
    if len(set(bucket_ids)) != len(bucket_ids):
        raise HTTPException(400, "duplicate bucket in allocations")
    rows = (
        await session.execute(
            select(AllocationBucket).where(AllocationBucket.id.in_(bucket_ids))
        )
    ).scalars().all()
    found = {b.id for b in rows}
    missing = set(bucket_ids) - found
    if missing:
        raise HTTPException(400, f"bucket not found: {sorted(missing)}")
    for a in allocations:
        if a.method == "percent" and a.value > 100:
            raise HTTPException(400, f"percent > 100 for bucket {a.bucket_id}")


async def _plan_out(session: AsyncSession, plan: MonthlyPlan) -> PlanOut:
    allocs = await get_allocations(session, plan.id)
    return PlanOut(
        id=plan.id,
        month=plan.month,
        expected_income=plan.expected_income,
        strategy=plan.strategy,
        carry_over_enabled=plan.carry_over_enabled,
        note=plan.note,
        allocations=[AllocationOut.model_validate(a) for a in allocs],
    )


@router.get("", response_model=list[PlanOut])
async def list_plans(session: AsyncSession = Depends(get_session)):
    rows = (
        (await session.execute(select(MonthlyPlan).order_by(MonthlyPlan.month.desc())))
        .scalars()
        .all()
    )
    return [await _plan_out(session, p) for p in rows]


@router.post("", response_model=PlanOut, status_code=201)
async def create_plan(data: PlanCreate, session: AsyncSession = Depends(get_session)):
    month = month_start(data.month)
    existing = await get_plan_by_month(session, month)
    if existing:
        raise HTTPException(409, f"plan already exists for {month}")
    await _validate_allocations(session, data.allocations)
    plan = await create_plan_with_allocs(
        session,
        month=month,
        expected_income=data.expected_income,
        strategy=data.strategy,
        carry_over_enabled=data.carry_over_enabled,
        note=data.note,
        allocations=data.allocations,
    )
    return await _plan_out(session, plan)


@router.get("/suggest-income", response_model=IncomeSuggestOut)
async def suggest_income_endpoint(
    month: str, session: AsyncSession = Depends(get_session)
):
    m = _parse_month(month)
    suggested, samples, method = await suggest_income(session, m)
    return IncomeSuggestOut(month=m, suggested=suggested, samples=samples, method=method)


@router.get("/{month}", response_model=PlanOut)
async def get_plan(month: str, session: AsyncSession = Depends(get_session)):
    m = _parse_month(month)
    plan = await get_plan_by_month(session, m)
    if not plan:
        raise HTTPException(404, f"no plan for {m}")
    return await _plan_out(session, plan)


@router.get("/{month}/summary", response_model=PlanSummaryOut)
async def summary(month: str, session: AsyncSession = Depends(get_session)):
    m = _parse_month(month)
    return await plan_summary(session, m)


@router.patch("/{month}", response_model=PlanOut)
async def update_plan(
    month: str, data: PlanUpdate, session: AsyncSession = Depends(get_session)
):
    m = _parse_month(month)
    plan = await get_plan_by_month(session, m)
    if not plan:
        raise HTTPException(404, f"no plan for {m}")
    patch = data.model_dump(exclude_unset=True)
    allocations = patch.pop("allocations", None)
    for k, v in patch.items():
        setattr(plan, k, v)
    if allocations is not None:
        await _validate_allocations(session, data.allocations or [])
        await replace_allocations(session, plan, data.allocations or [])
    await session.commit()
    await session.refresh(plan)
    return await _plan_out(session, plan)


@router.delete("/{month}", status_code=204)
async def delete_plan(month: str, session: AsyncSession = Depends(get_session)):
    m = _parse_month(month)
    plan = await get_plan_by_month(session, m)
    if not plan:
        raise HTTPException(404, f"no plan for {m}")
    await session.execute(
        PlanAllocation.__table__.delete().where(PlanAllocation.monthly_plan_id == plan.id)
    )
    await session.delete(plan)
    await session.commit()
    return None


@router.post("/{target_month}/copy-from/{source_month}", response_model=PlanOut, status_code=201)
async def copy_plan(
    target_month: str,
    source_month: str,
    session: AsyncSession = Depends(get_session),
):
    src = _parse_month(source_month)
    tgt = _parse_month(target_month)
    try:
        plan = await clone_plan(session, source_month=src, target_month=tgt)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return await _plan_out(session, plan)
