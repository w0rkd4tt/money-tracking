from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from .category import CategoryOut
from .transaction import TransactionOut


class KpiCard(BaseModel):
    label: str
    value: Decimal
    currency: str = "VND"
    delta_pct: float | None = None
    sparkline: list[Decimal] = []


class CashflowPoint(BaseModel):
    day: date
    expense: Decimal
    income: Decimal
    net_cumulative: Decimal


class CategoryBreakdown(BaseModel):
    category_id: int | None
    category_name: str
    total: Decimal
    pct: float
    count: int


class MerchantStat(BaseModel):
    merchant_id: int | None
    name: str
    total: Decimal
    count: int


class DashboardOverview(BaseModel):
    kpis: list[KpiCard]
    cashflow: list[CashflowPoint]
    breakdown: list[CategoryBreakdown]
    top_merchants: list[MerchantStat]


class CategoryStatsOut(BaseModel):
    category: CategoryOut
    period: str
    start: date
    end: date
    total: Decimal
    count: int
    avg_per_tx: Decimal
    cashflow: list[CashflowPoint]
    top_merchants: list[MerchantStat]
    transactions: list[TransactionOut]
