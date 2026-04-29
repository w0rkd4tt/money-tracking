from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category, Merchant, Transaction
from ..schemas.category import CategoryOut
from ..schemas.dashboard import (
    CashflowPoint,
    CategoryBreakdown,
    CategoryStatsOut,
    DashboardOverview,
    KpiCard,
    MerchantStat,
)
from ..schemas.transaction import TransactionOut
from .balances import compute_balances


Period = str  # "week" | "month" | "year"


def period_range(period: Period, today: date) -> tuple[datetime, datetime, str]:
    """Return (start, end_exclusive, bucket). bucket ∈ {"day","month"}."""
    if period == "week":
        monday = today - timedelta(days=today.weekday())
        start = datetime.combine(monday, datetime.min.time())
        end = start + timedelta(days=7)
        return start, end, "day"
    if period == "year":
        return (
            datetime(today.year, 1, 1),
            datetime(today.year + 1, 1, 1),
            "month",
        )
    # default: month
    start = datetime(today.year, today.month, 1)
    if today.month == 12:
        end = datetime(today.year + 1, 1, 1)
    else:
        end = datetime(today.year, today.month + 1, 1)
    return start, end, "day"


def _prev_period_range(period: Period, today: date) -> tuple[datetime, datetime]:
    if period == "week":
        start, end, _ = period_range("week", today - timedelta(days=7))
        return start, end
    if period == "year":
        return (
            datetime(today.year - 1, 1, 1),
            datetime(today.year, 1, 1),
        )
    # month
    first = datetime(today.year, today.month, 1)
    prev_last_day = first - timedelta(days=1)
    prev_first = datetime(prev_last_day.year, prev_last_day.month, 1)
    return prev_first, first


async def _expense_income(session: AsyncSession, start: datetime, end: datetime):
    # Transfers between the user's own accounts (e.g. Timo → HSBC credit-card
    # payment) are NOT spend/earn — exclude any tx that's part of a transfer
    # pair so the source and credit leg don't double-count as 8M expense for
    # what's really a 0-net internal move.
    q_exp = (
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Category.kind == "expense",
            Transaction.transfer_group_id.is_(None),
        )
    )
    q_inc = (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Category.kind == "income",
            Transaction.transfer_group_id.is_(None),
        )
    )
    exp = Decimal((await session.execute(q_exp)).scalar_one() or 0)
    inc = Decimal((await session.execute(q_inc)).scalar_one() or 0)
    return exp, inc


async def _cashflow_daily(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    category_id: int | None = None,
) -> list[tuple[date, Decimal, Decimal]]:
    day_col = func.date(Transaction.ts).label("day")
    q = (
        select(
            day_col,
            func.coalesce(
                func.sum(
                    case(
                        (Category.kind == "expense", func.abs(Transaction.amount)), else_=0
                    )
                ),
                0,
            ).label("expense"),
            func.coalesce(
                func.sum(case((Category.kind == "income", Transaction.amount), else_=0)),
                0,
            ).label("income"),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Transaction.transfer_group_id.is_(None),
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    if category_id is not None:
        q = q.where(Transaction.category_id == category_id)
    rows = (await session.execute(q)).all()
    out: list[tuple[date, Decimal, Decimal]] = []
    for r in rows:
        d = r.day if isinstance(r.day, date) else date.fromisoformat(str(r.day))
        out.append((d, Decimal(r.expense or 0), Decimal(r.income or 0)))
    return out


def _build_cashflow(
    raw: list[tuple[date, Decimal, Decimal]],
    start: datetime,
    end: datetime,
    bucket: str,
) -> list[CashflowPoint]:
    """Fill missing slots with zeros + compute cumulative."""
    if bucket == "day":
        by_key: dict[date, tuple[Decimal, Decimal]] = {}
        d = start.date()
        while d < end.date():
            by_key[d] = (Decimal(0), Decimal(0))
            d += timedelta(days=1)
        for day, exp, inc in raw:
            if day in by_key:
                by_key[day] = (exp, inc)
        pts: list[CashflowPoint] = []
        running = Decimal(0)
        for key in sorted(by_key):
            exp, inc = by_key[key]
            running += inc - exp
            pts.append(
                CashflowPoint(day=key, expense=exp, income=inc, net_cumulative=running)
            )
        return pts

    # bucket == "month"
    by_month: dict[str, tuple[Decimal, Decimal]] = {}
    y = start.year
    for m in range(1, 13):
        by_month[f"{y}-{m:02d}"] = (Decimal(0), Decimal(0))
    for day, exp, inc in raw:
        key = f"{day.year}-{day.month:02d}"
        prev_e, prev_i = by_month.get(key, (Decimal(0), Decimal(0)))
        by_month[key] = (prev_e + exp, prev_i + inc)
    pts = []
    running = Decimal(0)
    for key in sorted(by_month):
        exp, inc = by_month[key]
        running += inc - exp
        year_s, month_s = key.split("-")
        pts.append(
            CashflowPoint(
                day=date(int(year_s), int(month_s), 1),
                expense=exp,
                income=inc,
                net_cumulative=running,
            )
        )
    return pts


async def _breakdown(
    session: AsyncSession, start: datetime, end: datetime, limit: int = 20
) -> list[CategoryBreakdown]:
    q = (
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Category.kind == "expense",
            Transaction.transfer_group_id.is_(None),
        )
        .group_by(Category.id, Category.name)
        .order_by(desc("total"))
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    tot = sum((Decimal(r.total or 0) for r in rows), Decimal("0")) or Decimal("1")
    return [
        CategoryBreakdown(
            category_id=r.id,
            category_name=r.name,
            total=Decimal(r.total or 0),
            pct=float(Decimal(r.total or 0) / tot * 100),
            count=int(r.cnt or 0),
        )
        for r in rows
    ]


async def _top_merchants(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    limit: int = 5,
    category_id: int | None = None,
) -> list[MerchantStat]:
    q = (
        select(
            Merchant.id,
            Merchant.name,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .join(Merchant, Merchant.id == Transaction.merchant_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Transaction.merchant_id.is_not(None),
            (Category.kind == "expense") | (Category.kind.is_(None)),
            Transaction.transfer_group_id.is_(None),
        )
        .group_by(Merchant.id, Merchant.name)
        .order_by(desc("total"))
        .limit(limit)
    )
    if category_id is not None:
        q = q.where(Transaction.category_id == category_id)
    rows = (await session.execute(q)).all()
    return [
        MerchantStat(
            merchant_id=r.id, name=r.name, total=Decimal(r.total or 0), count=int(r.cnt or 0)
        )
        for r in rows
    ]


async def category_stats(
    session: AsyncSession,
    category_id: int,
    period: Period = "month",
    today: date | None = None,
    transactions_limit: int = 50,
) -> CategoryStatsOut:
    cat = await session.get(Category, category_id)
    if cat is None:
        raise LookupError(f"category {category_id} not found")

    today = today or date.today()
    start, end, bucket = period_range(period, today)

    raw = await _cashflow_daily(session, start, end, category_id=category_id)
    cashflow = _build_cashflow(raw, start, end, bucket)

    agg_q = select(
        func.coalesce(func.sum(func.abs(Transaction.amount)), 0),
        func.count(Transaction.id),
    ).where(
        Transaction.ts >= start,
        Transaction.ts < end,
        Transaction.status == "confirmed",
        Transaction.category_id == category_id,
    )
    total_val, count_val = (await session.execute(agg_q)).one()
    total = Decimal(total_val or 0)
    count = int(count_val or 0)
    avg = (total / count) if count else Decimal(0)

    top_merchants = await _top_merchants(session, start, end, category_id=category_id)

    txs_q = (
        select(Transaction)
        .where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.category_id == category_id,
        )
        .order_by(desc(Transaction.ts), desc(Transaction.id))
        .limit(transactions_limit)
    )
    tx_rows = (await session.execute(txs_q)).scalars().all()
    tx_outs = [TransactionOut.model_validate(t) for t in tx_rows]

    return CategoryStatsOut(
        category=CategoryOut.model_validate(cat),
        period=period,
        start=start.date(),
        end=end.date(),
        total=total,
        count=count,
        avg_per_tx=avg,
        cashflow=cashflow,
        top_merchants=top_merchants,
        transactions=tx_outs,
    )


async def overview(
    session: AsyncSession,
    period: Period = "month",
    today: date | None = None,
) -> DashboardOverview:
    today = today or date.today()
    start, end, bucket = period_range(period, today)
    prev_start, prev_end = _prev_period_range(period, today)

    total_expense, total_income = await _expense_income(session, start, end)
    prev_expense, prev_income = await _expense_income(session, prev_start, prev_end)

    def _pct(cur: Decimal, prev: Decimal) -> float | None:
        if prev == 0:
            return None
        return float((cur - prev) / prev * 100)

    balances = await compute_balances(session)
    total_assets = sum((b.balance for b in balances), Decimal("0"))
    net = total_income - total_expense

    label_prefix = {"week": "Tuần", "month": "Tháng", "year": "Năm"}.get(period, "Kỳ")

    kpis = [
        KpiCard(label="Tổng tài sản", value=Decimal(total_assets)),
        KpiCard(
            label=f"Chi {label_prefix.lower()}",
            value=Decimal(total_expense),
            delta_pct=_pct(total_expense, prev_expense),
        ),
        KpiCard(
            label=f"Thu {label_prefix.lower()}",
            value=Decimal(total_income),
            delta_pct=_pct(total_income, prev_income),
        ),
        KpiCard(label="Net", value=Decimal(net)),
    ]

    raw = await _cashflow_daily(session, start, end)
    cashflow = _build_cashflow(raw, start, end, bucket)
    breakdown = await _breakdown(session, start, end)
    top_merchants = await _top_merchants(session, start, end)

    return DashboardOverview(
        kpis=kpis,
        cashflow=cashflow,
        breakdown=breakdown,
        top_merchants=top_merchants,
    )


async def range_stats(session: AsyncSession, from_: datetime, to: datetime) -> dict:
    exp, inc = await _expense_income(session, from_, to)
    q_cnt = (
        select(func.count(Transaction.id))
        .where(Transaction.ts >= from_, Transaction.ts < to, Transaction.status == "confirmed")
    )
    cnt = (await session.execute(q_cnt)).scalar_one() or 0
    return {
        "total_expense": exp,
        "total_income": inc,
        "net": inc - exp,
        "count": int(cnt),
    }


async def last_n_days(session: AsyncSession, days: int = 30) -> list[CashflowPoint]:
    end = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    start = end - timedelta(days=days)
    raw = await _cashflow_daily(session, start, end)
    return _build_cashflow(raw, start, end, "day")
