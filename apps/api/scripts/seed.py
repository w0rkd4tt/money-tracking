"""Seed default accounts, categories, Gmail allowlist policies.

Run: docker compose exec api python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from money_api.config import get_settings  # noqa: E402
from money_api.db import SessionLocal  # noqa: E402
from money_api.models import (  # noqa: E402
    Account,
    AppSetting,
    Category,
    LlmGmailPolicy,
)


DEFAULT_ACCOUNTS = [
    {"name": "Tiền mặt", "type": "cash", "icon": "💵", "color": "#6b7280", "is_default": True},
    {"name": "VCB", "type": "bank", "icon": "🏦", "color": "#1d4ed8"},
    {"name": "TCB", "type": "bank", "icon": "🏦", "color": "#059669"},
    {"name": "Momo", "type": "ewallet", "icon": "🅼", "color": "#ec4899"},
]

# Root-then-leaf; children parented by name.
DEFAULT_CATEGORIES: list[tuple[str, str, str | None, str | None]] = [
    ("Ăn uống", "expense", None, "🍜"),
    ("Sáng", "expense", "Ăn uống", "☕"),
    ("Trưa", "expense", "Ăn uống", "🍚"),
    ("Tối", "expense", "Ăn uống", "🍜"),
    ("Đi lại", "expense", None, "🚗"),
    ("Grab", "expense", "Đi lại", None),
    ("Xăng xe", "expense", "Đi lại", None),
    ("Hoá đơn", "expense", None, "💡"),
    ("Điện nước", "expense", "Hoá đơn", None),
    ("Internet", "expense", "Hoá đơn", None),
    ("Điện thoại", "expense", "Hoá đơn", None),
    ("Mua sắm", "expense", None, "🛒"),
    ("Online", "expense", "Mua sắm", None),
    ("Giải trí", "expense", None, "🎮"),
    ("Sức khoẻ", "expense", None, "💊"),
    ("Giáo dục", "expense", None, "📚"),
    ("Lương", "income", None, "💰"),
    ("Thưởng", "income", None, "🎁"),
    ("Đầu tư", "income", None, "📈"),
    ("Hoàn tiền", "income", None, "↩️"),
    ("Khác", "expense", None, None),
    ("Transfer", "transfer", None, "⇄"),
    ("Chưa phân loại", "expense", None, "❓"),
    # Credit card expense bucket (used when Gmail maps to a credit account).
    ("Dư nợ thẻ tín dụng", "expense", None, "💳"),
    ("Thanh toán thẻ TD", "expense", "Dư nợ thẻ tín dụng", "💵"),
]


# Gmail allowlist for the configured target email.
# Deny-by-default, but seed conservative defaults so user can turn on LLM Gmail
# tool after reviewing in UI.
DEFAULT_GMAIL_POLICIES: list[dict] = [
    # Common VN banks / wallets (disabled by default — user enables after reviewing)
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@vcbonline.com.vn",
        "priority": 100,
        "enabled": False,
        "note": "Vietcombank — bật sau khi verify email này thực sự đến account",
    },
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@techcombank.com.vn",
        "priority": 100,
        "enabled": False,
        "note": "Techcombank",
    },
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@mbbank.com.vn",
        "priority": 100,
        "enabled": False,
        "note": "MB Bank",
    },
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@tpb.com.vn",
        "priority": 100,
        "enabled": False,
        "note": "TPBank",
    },
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@momo.vn",
        "priority": 100,
        "enabled": False,
        "note": "Momo",
    },
    {
        "action": "allow",
        "pattern_type": "from",
        "pattern": "*@shopee.vn",
        "priority": 100,
        "enabled": False,
        "note": "Shopee",
    },
    # Always-on denies (take priority)
    {
        "action": "deny",
        "pattern_type": "subject",
        "pattern": "OTP",
        "priority": 1000,
        "enabled": True,
        "note": "Never expose OTP content to LLM",
    },
    {
        "action": "deny",
        "pattern_type": "subject",
        "pattern": "mã xác thực",
        "priority": 1000,
        "enabled": True,
        "note": "Verification codes",
    },
    {
        "action": "deny",
        "pattern_type": "subject",
        "pattern": "verification code",
        "priority": 1000,
        "enabled": True,
    },
]


async def seed() -> None:
    print("→ Seeding…")
    async with SessionLocal() as session:
        # Accounts
        existing = (await session.execute(select(Account.name))).scalars().all()
        existing_set = set(existing)
        for a in DEFAULT_ACCOUNTS:
            if a["name"] in existing_set:
                continue
            session.add(Account(**a, opening_balance=Decimal("0")))
        await session.flush()
        print(f"  accounts: +{len(DEFAULT_ACCOUNTS) - len(existing_set)}")

        # Categories — two-pass for parent resolution
        existing_cat = (await session.execute(select(Category.name, Category.id))).all()
        name_to_id = {r.name: r.id for r in existing_cat}
        added = 0
        # Pass 1: roots first
        for name, kind, parent_name, icon in DEFAULT_CATEGORIES:
            if parent_name is not None or name in name_to_id:
                continue
            cat = Category(name=name, kind=kind, icon=icon, path=name)
            session.add(cat)
            await session.flush()
            name_to_id[name] = cat.id
            added += 1
        # Pass 2: children
        for name, kind, parent_name, icon in DEFAULT_CATEGORIES:
            if parent_name is None or name in name_to_id:
                continue
            parent_id = name_to_id.get(parent_name)
            if parent_id is None:
                continue
            cat = Category(
                name=name,
                kind=kind,
                parent_id=parent_id,
                icon=icon,
                path=f"{parent_name} > {name}",
            )
            session.add(cat)
            await session.flush()
            name_to_id[name] = cat.id
            added += 1
        print(f"  categories: +{added}")

        # Gmail policies
        existing_pols = (
            await session.execute(select(LlmGmailPolicy.pattern, LlmGmailPolicy.action))
        ).all()
        pol_set = {(r.pattern, r.action) for r in existing_pols}
        pol_added = 0
        for p in DEFAULT_GMAIL_POLICIES:
            key = (p["pattern"], p["action"])
            if key in pol_set:
                continue
            session.add(LlmGmailPolicy(**p))
            pol_added += 1
        print(f"  llm_gmail_policy: +{pol_added}")

        # App setting singleton
        current = (
            await session.execute(select(AppSetting).where(AppSetting.id == 1))
        ).scalar_one_or_none()
        if current is None:
            s = get_settings()
            session.add(
                AppSetting(
                    id=1,
                    locale=s.locale,
                    timezone=s.tz,
                    default_currency=s.default_currency,
                )
            )
            print("  app_setting: initialized")

        await session.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
