"""Seed default allocation buckets + current-month plan.

Run: docker compose exec api python -m scripts.seed_plan

Idempotent: skips buckets/plan/allocations that already exist by their
natural keys (bucket name, plan month, plan+bucket pair).

Default strategy is a slight Vietnam-localised variant of 50/30/20:
  - 50% Thiết yếu  (essentials — must-pay each month)
  - 25% Linh hoạt  (discretionary — lifestyle, learning)
  - 20% Tiết kiệm  (savings & investing — pay yourself first)
  -  5% Trả nợ thẻ (credit-card debt buffer; if you don't carry a balance
                    the rollover lets it accumulate as a buffer instead)
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from money_api.db import SessionLocal  # noqa: E402
from money_api.models import (  # noqa: E402
    AllocationBucket,
    BucketCategory,
    Category,
    MonthlyPlan,
    PlanAllocation,
)


# (name, icon, color, sort_order, percent of expected income)
BUCKETS: list[tuple[str, str, str, int, Decimal]] = [
    ("Thiết yếu", "🏠", "#ef4444", 10, Decimal("50")),
    ("Linh hoạt", "🎉", "#f59e0b", 20, Decimal("25")),
    ("Tiết kiệm & Đầu tư", "💰", "#10b981", 30, Decimal("20")),
    ("Trả nợ thẻ TD", "💳", "#6366f1", 40, Decimal("5")),
]

# Bucket name → list of category names that map into it. Names must match
# DEFAULT_CATEGORIES in seed.py exactly. Categories not listed remain
# unmapped (e.g. "Lương", "Thưởng" are income, not allocations).
BUCKET_CATEGORIES: dict[str, list[str]] = {
    "Thiết yếu": [
        "Ăn uống", "Sáng", "Trưa", "Tối",
        "Đi lại", "Grab", "Xăng xe",
        "Hoá đơn", "Điện nước", "Internet", "Điện thoại",
        "Nhà ở", "Tiền thuê",
        "Sức khoẻ",
    ],
    "Linh hoạt": [
        "Mua sắm", "Online",
        "Giải trí",
        "Giáo dục",
        "Khác",
    ],
    "Trả nợ thẻ TD": [
        "Dư nợ thẻ tín dụng",
        "Thanh toán thẻ TD",
    ],
    # "Tiết kiệm & Đầu tư" intentionally has no categories — it's a
    # forward-looking allocation, not retro spend tracking.
}


async def seed_plan() -> None:
    print("→ Seeding buckets + current-month plan…")
    async with SessionLocal() as session:
        # ---- Buckets -------------------------------------------------------
        existing = {
            row.name: row.id
            for row in (
                await session.execute(select(AllocationBucket.name, AllocationBucket.id))
            ).all()
        }
        bucket_ids: dict[str, int] = dict(existing)
        created_buckets = 0
        for name, icon, color, sort_order, _pct in BUCKETS:
            if name in bucket_ids:
                continue
            b = AllocationBucket(
                name=name, icon=icon, color=color, sort_order=sort_order
            )
            session.add(b)
            await session.flush()
            bucket_ids[name] = b.id
            created_buckets += 1
        print(f"  buckets: +{created_buckets}")

        # ---- Bucket → category mapping ------------------------------------
        cat_name_to_id = {
            row.name: row.id
            for row in (
                await session.execute(select(Category.name, Category.id))
            ).all()
        }
        existing_links = {
            (row.bucket_id, row.category_id)
            for row in (
                await session.execute(
                    select(BucketCategory.bucket_id, BucketCategory.category_id)
                )
            ).all()
        }
        created_links = 0
        for bucket_name, cat_names in BUCKET_CATEGORIES.items():
            bid = bucket_ids.get(bucket_name)
            if bid is None:
                continue
            for cn in cat_names:
                cid = cat_name_to_id.get(cn)
                if cid is None:
                    print(f"  ⚠ category '{cn}' not found, skipping")
                    continue
                if (bid, cid) in existing_links:
                    continue
                session.add(BucketCategory(bucket_id=bid, category_id=cid))
                created_links += 1
        print(f"  bucket_category: +{created_links}")

        # ---- Monthly plan (current month) ---------------------------------
        today = date.today()
        month_start = today.replace(day=1)
        plan = (
            await session.execute(
                select(MonthlyPlan).where(MonthlyPlan.month == month_start)
            )
        ).scalar_one_or_none()
        if plan is None:
            plan = MonthlyPlan(
                month=month_start,
                expected_income=Decimal("0"),
                strategy="soft",
                carry_over_enabled=True,
                note=(
                    "Plan mặc định 50/25/20/5. Cập nhật `expected_income` ở "
                    "/plans để hệ thống tính ra số VND tương ứng cho từng bucket."
                ),
            )
            session.add(plan)
            await session.flush()
            print(f"  monthly_plan: created for {month_start}")
        else:
            print(f"  monthly_plan: exists for {month_start} (skipped)")

        # ---- Allocations (percent of expected income) ---------------------
        existing_allocs = {
            row.bucket_id
            for row in (
                await session.execute(
                    select(PlanAllocation.bucket_id).where(
                        PlanAllocation.monthly_plan_id == plan.id
                    )
                )
            ).all()
        }
        created_allocs = 0
        for name, _icon, _color, _sort, pct in BUCKETS:
            bid = bucket_ids.get(name)
            if bid is None or bid in existing_allocs:
                continue
            session.add(
                PlanAllocation(
                    monthly_plan_id=plan.id,
                    bucket_id=bid,
                    method="percent",
                    value=pct,
                    rollover=True,
                )
            )
            created_allocs += 1
        print(f"  plan_allocation: +{created_allocs}")

        await session.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed_plan())
