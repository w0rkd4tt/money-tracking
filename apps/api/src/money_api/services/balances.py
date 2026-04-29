from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, Transaction
from ..schemas import BalanceOut


async def compute_balances(session: AsyncSession) -> list[BalanceOut]:
    subq = (
        select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0).label("sum"))
        .where(Transaction.status == "confirmed")
        .group_by(Transaction.account_id)
        .subquery()
    )
    q = (
        select(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            Account.opening_balance,
            Account.credit_limit,
            subq.c.sum,
        )
        .outerjoin(subq, subq.c.account_id == Account.id)
        .where(Account.archived.is_(False))
        .order_by(Account.id)
    )
    rows = (await session.execute(q)).all()

    out: list[BalanceOut] = []
    for r in rows:
        balance = (r.opening_balance or Decimal("0")) + (r.sum or Decimal("0"))
        debt = None
        available = None
        util = None
        if r.type == "credit":
            # Convention: credit account balance goes NEGATIVE as you spend;
            # 0 after payoff. `debt` is just the positive magnitude of that
            # negative — works regardless of whether the user has filled in
            # `credit_limit`. Without a limit we just can't compute the
            # available/utilisation pair.
            debt = max(Decimal("0"), -balance)
            if r.credit_limit and r.credit_limit > 0:
                available = r.credit_limit - debt
                util = float(debt / r.credit_limit * 100)
        out.append(
            BalanceOut(
                account_id=r.id,
                name=r.name,
                type=r.type,
                currency=r.currency,
                balance=balance,
                credit_limit=r.credit_limit,
                debt=debt,
                available_credit=available,
                utilization_pct=util,
            )
        )
    return out
