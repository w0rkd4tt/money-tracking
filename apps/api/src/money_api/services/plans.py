from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AllocationBucket,
    BucketCategory,
    Category,
    MonthlyPlan,
    PlanAllocation,
    Transaction,
)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def next_month(d: date) -> date:
    d = month_start(d)
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def prev_month(d: date) -> date:
    d = month_start(d)
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def month_window(d: date) -> tuple[datetime, datetime]:
    start = month_start(d)
    end = next_month(start)
    return datetime(start.year, start.month, 1), datetime(end.year, end.month, 1)


async def actual_income(session: AsyncSession, month: date) -> Decimal:
    """Sum of absolute amounts for confirmed transactions in month whose category is income."""
    start, end = month_window(month)
    q = (
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Category.kind == "income",
        )
    )
    v = (await session.execute(q)).scalar_one() or 0
    return Decimal(v).quantize(Decimal("0.01"))


async def suggest_income(session: AsyncSession, month: date) -> tuple[Decimal, list[dict], str]:
    """Suggest expected_income as average actual_income of previous 3 months.
    Falls back to 0 if no history.
    """
    samples: list[dict] = []
    cur = month_start(month)
    for _ in range(3):
        cur = prev_month(cur)
        inc = await actual_income(session, cur)
        samples.append({"month": cur, "income": inc})

    positives = [s["income"] for s in samples if s["income"] > 0]
    if positives:
        avg = sum(positives) / Decimal(len(positives))
        # round to nearest 1000 VND for friendliness
        avg = (avg / Decimal(1000)).quantize(Decimal("1")) * Decimal(1000)
        return avg.quantize(Decimal("0.01")), samples, "avg_3m"
    return Decimal("0.00"), samples, "fallback"


async def spend_by_category(session: AsyncSession, month: date) -> dict[int, Decimal]:
    """Map category_id → absolute spend in the month (expense categories only, confirmed tx)."""
    start, end = month_window(month)
    q = (
        select(
            Transaction.category_id,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Category.kind == "expense",
        )
        .group_by(Transaction.category_id)
    )
    rows = (await session.execute(q)).all()
    return {r.category_id: Decimal(r.total or 0).quantize(Decimal("0.01")) for r in rows}


async def bucket_to_categories(session: AsyncSession) -> dict[int, list[int]]:
    rows = (await session.execute(select(BucketCategory))).scalars().all()
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(r.bucket_id, []).append(r.category_id)
    return out


async def get_plan_by_month(session: AsyncSession, month: date) -> MonthlyPlan | None:
    m = month_start(month)
    q = select(MonthlyPlan).where(MonthlyPlan.month == m)
    return (await session.execute(q)).scalar_one_or_none()


async def get_allocations(session: AsyncSession, plan_id: int) -> list[PlanAllocation]:
    q = select(PlanAllocation).where(PlanAllocation.monthly_plan_id == plan_id)
    return list((await session.execute(q)).scalars().all())


def resolve_allocated(alloc: PlanAllocation, expected_income: Decimal) -> Decimal:
    if alloc.method == "percent":
        return (expected_income * alloc.value / Decimal(100)).quantize(Decimal("0.01"))
    return Decimal(alloc.value).quantize(Decimal("0.01"))


async def _bucket_remaining(
    session: AsyncSession, plan: MonthlyPlan, bucket_id: int
) -> Decimal:
    """Compute (allocated − spent) for a bucket in `plan`. Signed."""
    alloc = (
        await session.execute(
            select(PlanAllocation).where(
                PlanAllocation.monthly_plan_id == plan.id,
                PlanAllocation.bucket_id == bucket_id,
            )
        )
    ).scalar_one_or_none()
    if not alloc:
        return Decimal("0")
    allocated = resolve_allocated(alloc, plan.expected_income)

    b2c = await bucket_to_categories(session)
    cat_ids = b2c.get(bucket_id, [])
    if not cat_ids:
        return allocated

    spend = await spend_by_category(session, plan.month)
    spent = sum((spend.get(c, Decimal("0")) for c in cat_ids), Decimal("0"))
    return allocated - spent


async def carry_in_for(
    session: AsyncSession, plan: MonthlyPlan, bucket_id: int, rollover: bool
) -> Decimal:
    """Look back one month and return (prev_allocated − prev_spent) if rollover is on.
    Positive = dư mang sang, negative = vượt trừ sang.
    """
    if not plan.carry_over_enabled or not rollover:
        return Decimal("0")
    prev_m = prev_month(plan.month)
    prev_plan = await get_plan_by_month(session, prev_m)
    if not prev_plan:
        return Decimal("0")
    return await _bucket_remaining(session, prev_plan, bucket_id)


async def plan_summary(session: AsyncSession, month: date) -> dict:
    from ..schemas.plan import BucketStatusOut, PlanSummaryOut

    m = month_start(month)
    plan = await get_plan_by_month(session, m)

    actual = await actual_income(session, m)
    spend = await spend_by_category(session, m)
    b2c = await bucket_to_categories(session)

    buckets_rows = (
        await session.execute(
            select(AllocationBucket).where(AllocationBucket.archived.is_(False))
            .order_by(AllocationBucket.sort_order, AllocationBucket.id)
        )
    ).scalars().all()

    allocations_by_bucket: dict[int, PlanAllocation] = {}
    if plan:
        for a in await get_allocations(session, plan.id):
            allocations_by_bucket[a.bucket_id] = a

    expected_income = plan.expected_income if plan else Decimal("0")
    strategy = plan.strategy if plan else "soft"
    total_allocated = Decimal("0.00")
    total_spent_bucketed = Decimal("0.00")

    bucket_statuses: list[BucketStatusOut] = []
    for b in buckets_rows:
        alloc = allocations_by_bucket.get(b.id)
        if alloc:
            allocated = resolve_allocated(alloc, expected_income)
            rollover = alloc.rollover
            method = alloc.method
            raw_value = alloc.value
        else:
            allocated = Decimal("0")
            rollover = False
            method = "amount"
            raw_value = Decimal("0")

        cat_ids = b2c.get(b.id, [])
        spent = sum((spend.get(c, Decimal("0")) for c in cat_ids), Decimal("0"))

        carry = Decimal("0")
        if plan and rollover:
            carry = await carry_in_for(session, plan, b.id, rollover)

        denom = allocated + carry
        remaining = denom - spent
        pct = float(spent / denom * 100) if denom > 0 else (100.0 if spent > 0 else 0.0)

        if allocated == 0 and carry == 0:
            status = "unplanned"
        elif pct >= 100:
            status = "over"
        elif pct >= 80:
            status = "warn"
        else:
            status = "ok"

        total_allocated += allocated
        total_spent_bucketed += spent

        bucket_statuses.append(
            BucketStatusOut(
                bucket_id=b.id,
                bucket_name=b.name,
                method=method,
                value=raw_value,
                allocated=allocated,
                spent=spent,
                carry_in=carry,
                remaining=remaining,
                pct=pct,
                status=status,
                rollover=rollover,
            )
        )

    # unplanned spent = total expense in month minus what's covered by buckets
    total_expense = sum(spend.values(), Decimal("0.00")).quantize(Decimal("0.01"))
    unplanned = (total_expense - total_spent_bucketed).quantize(Decimal("0.01"))

    return PlanSummaryOut(
        month=m,
        strategy=strategy,
        expected_income=expected_income,
        actual_income=actual,
        total_allocated=total_allocated,
        total_spent=total_expense,
        unplanned_spent=unplanned,
        buckets=bucket_statuses,
    ).model_dump()


async def create_plan_with_allocs(
    session: AsyncSession,
    *,
    month: date,
    expected_income: Decimal,
    strategy: str,
    carry_over_enabled: bool,
    note: str | None,
    allocations: list,
) -> MonthlyPlan:
    plan = MonthlyPlan(
        month=month_start(month),
        expected_income=expected_income,
        strategy=strategy,
        carry_over_enabled=carry_over_enabled,
        note=note,
    )
    session.add(plan)
    await session.flush()
    for a in allocations:
        session.add(
            PlanAllocation(
                monthly_plan_id=plan.id,
                bucket_id=a.bucket_id,
                method=a.method,
                value=a.value,
                rollover=a.rollover,
                note=a.note,
            )
        )
    await session.commit()
    await session.refresh(plan)
    return plan


async def replace_allocations(
    session: AsyncSession, plan: MonthlyPlan, allocations: list
) -> None:
    await session.execute(
        PlanAllocation.__table__.delete().where(PlanAllocation.monthly_plan_id == plan.id)
    )
    for a in allocations:
        session.add(
            PlanAllocation(
                monthly_plan_id=plan.id,
                bucket_id=a.bucket_id,
                method=a.method,
                value=a.value,
                rollover=a.rollover,
                note=a.note,
            )
        )


async def clone_plan(
    session: AsyncSession, *, source_month: date, target_month: date
) -> MonthlyPlan:
    src = await get_plan_by_month(session, source_month)
    if not src:
        raise LookupError(f"no plan for {source_month}")
    target = month_start(target_month)
    existing = await get_plan_by_month(session, target)
    if existing:
        raise ValueError(f"plan already exists for {target}")

    plan = MonthlyPlan(
        month=target,
        expected_income=src.expected_income,
        strategy=src.strategy,
        carry_over_enabled=src.carry_over_enabled,
        note=src.note,
    )
    session.add(plan)
    await session.flush()
    for a in await get_allocations(session, src.id):
        session.add(
            PlanAllocation(
                monthly_plan_id=plan.id,
                bucket_id=a.bucket_id,
                method=a.method,
                value=a.value,
                rollover=a.rollover,
                note=a.note,
            )
        )
    await session.commit()
    await session.refresh(plan)
    return plan
