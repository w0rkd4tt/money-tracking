from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Budget, Category, Transaction
from ..schemas.budget import BudgetStatusOut


def _monthly_window(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, 1)
    if d.month == 12:
        end = datetime(d.year + 1, 1, 1)
    else:
        end = datetime(d.year, d.month + 1, 1)
    return start, end


async def statuses(session: AsyncSession, today: date | None = None) -> list[BudgetStatusOut]:
    today = today or date.today()
    start, end = _monthly_window(today)

    q_budgets = select(Budget).where(Budget.period == "monthly")
    budgets = (await session.execute(q_budgets)).scalars().all()

    result: list[BudgetStatusOut] = []
    for b in budgets:
        q = select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            Transaction.ts >= start,
            Transaction.ts < end,
            Transaction.status == "confirmed",
            Transaction.category_id == b.category_id if b.category_id else True,
        )
        spent = (await session.execute(q)).scalar_one() or Decimal("0")
        spent_dec = Decimal(spent)
        pct = float(spent_dec / b.limit_amount * 100) if b.limit_amount else 0.0

        name = None
        if b.category_id:
            cat = (
                await session.execute(select(Category.name).where(Category.id == b.category_id))
            ).scalar_one_or_none()
            name = cat

        status = "ok"
        if pct >= 100:
            status = "over"
        elif pct >= 80:
            status = "warn"

        result.append(
            BudgetStatusOut(
                budget_id=b.id,
                category_id=b.category_id,
                category_name=name,
                period=b.period,
                period_start=start.date(),
                limit_amount=b.limit_amount,
                spent=spent_dec,
                remaining=b.limit_amount - spent_dec,
                pct=pct,
                status=status,
            )
        )
    return result
