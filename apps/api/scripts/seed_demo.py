"""Seed demo transactions spanning the current year for visual testing
of dashboard charts (week/month/year views).

Run: docker compose exec api python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from money_api.db import SessionLocal  # noqa: E402
from money_api.models import Account, Category, Transaction  # noqa: E402


EXPENSE_MIX = [
    ("Ăn uống > Trưa", 40000, 90000),
    ("Ăn uống > Sáng", 20000, 50000),
    ("Ăn uống > Tối", 50000, 180000),
    ("Đi lại > Grab", 30000, 120000),
    ("Đi lại > Xăng xe", 100000, 250000),
    ("Hoá đơn > Điện nước", 300000, 900000),
    ("Hoá đơn > Internet", 200000, 300000),
    ("Mua sắm > Online", 100000, 800000),
    ("Giải trí", 100000, 500000),
]

INCOME_MIX = [
    ("Lương", 20_000_000, 35_000_000),
    ("Thưởng", 2_000_000, 8_000_000),
]


async def main() -> None:
    random.seed(42)
    async with SessionLocal() as session:
        # Skip if demo already seeded
        existing = (
            await session.execute(select(Transaction).where(Transaction.source == "seed_demo"))
        ).first()
        if existing:
            print("demo already seeded — skipping")
            return

        accts = (await session.execute(select(Account))).scalars().all()
        cats = (await session.execute(select(Category))).scalars().all()
        by_path = {c.path: c for c in cats}

        def pick_acc(for_kind: str) -> Account:
            if for_kind == "income":
                for a in accts:
                    if a.type == "bank":
                        return a
            pool = [a for a in accts if not a.archived]
            return random.choice(pool)

        count = 0
        today = datetime.now().replace(second=0, microsecond=0, tzinfo=None)
        start = today - timedelta(days=365)

        # Income: monthly salary + occasional bonus
        for months_back in range(12):
            d = (today.replace(day=1) - timedelta(days=30 * months_back)).replace(
                hour=9, minute=0
            )
            # salary
            lo, hi = 22_000_000, 28_000_000
            amount = random.randint(lo, hi)
            cat = by_path.get("Lương")
            if cat:
                session.add(
                    Transaction(
                        ts=d,
                        amount=Decimal(amount),
                        account_id=pick_acc("income").id,
                        category_id=cat.id,
                        merchant_text="Salary",
                        source="seed_demo",
                        status="confirmed",
                    )
                )
                count += 1
            # bonus 30%
            if random.random() < 0.3:
                cat = by_path.get("Thưởng")
                if cat:
                    session.add(
                        Transaction(
                            ts=d + timedelta(hours=6),
                            amount=Decimal(random.randint(1_000_000, 5_000_000)),
                            account_id=pick_acc("income").id,
                            category_id=cat.id,
                            merchant_text="Bonus",
                            source="seed_demo",
                            status="confirmed",
                        )
                    )
                    count += 1

        # Expenses: ~3-8 per day over 365 days
        d = start
        while d < today:
            per_day = random.randint(1, 8)
            for _ in range(per_day):
                path, lo, hi = random.choice(EXPENSE_MIX)
                cat = by_path.get(path)
                if cat is None:
                    # fallback: any expense category
                    pool = [c for c in cats if c.kind == "expense"]
                    if not pool:
                        continue
                    cat = random.choice(pool)
                amount = random.randint(lo, hi)
                hour = random.randint(7, 22)
                minute = random.choice([0, 15, 30, 45])
                ts = d.replace(hour=hour, minute=minute)
                session.add(
                    Transaction(
                        ts=ts,
                        amount=Decimal(-amount),
                        account_id=pick_acc("expense").id,
                        category_id=cat.id,
                        merchant_text=path.split(">")[-1].strip().lower() + " shop",
                        source="seed_demo",
                        status="confirmed",
                    )
                )
                count += 1
            d += timedelta(days=1)
        await session.commit()
        print(f"seeded {count} demo transactions over last 365 days")


if __name__ == "__main__":
    asyncio.run(main())
