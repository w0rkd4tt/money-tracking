from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Transaction
from ..schemas.common import PaginatedResponse
from ..schemas.transaction import (
    TransactionCreate,
    TransactionOut,
    TransactionStats,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


SortField = Literal["ts", "amount", "created_at"]
SortOrder = Literal["asc", "desc"]


@router.get("", response_model=PaginatedResponse[TransactionOut])
async def list_transactions(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    account_id: int | None = None,
    category_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: SortField = "ts",
    order: SortOrder = "desc",
    page: int = 1,
    size: int = 50,
    session: AsyncSession = Depends(get_session),
):
    filters = []
    if from_:
        filters.append(Transaction.ts >= datetime.combine(from_, datetime.min.time()))
    if to:
        filters.append(Transaction.ts < datetime.combine(to + timedelta(days=1), datetime.min.time()))
    if account_id:
        filters.append(Transaction.account_id == account_id)
    if category_id:
        filters.append(Transaction.category_id == category_id)
    if status:
        filters.append(Transaction.status == status)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(Transaction.merchant_text.ilike(like), Transaction.note.ilike(like))
        )

    base = select(Transaction).where(and_(*filters)) if filters else select(Transaction)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    # Build order: primary column + stable secondary tiebreaker on id (same direction).
    sort_cols = {
        "ts": Transaction.ts,
        "amount": Transaction.amount,
        "created_at": Transaction.created_at,
    }
    col = sort_cols[sort]
    dir_ = asc if order == "asc" else desc
    ordered = base.order_by(dir_(col), dir_(Transaction.id))

    rows = (
        await session.execute(
            ordered.offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    items = [TransactionOut.model_validate(r) for r in rows]
    return PaginatedResponse[TransactionOut](
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total,
    )


@router.get("/stats", response_model=TransactionStats)
async def stats(
    from_: date = Query(alias="from"),
    to: date = Query(...),
    session: AsyncSession = Depends(get_session),
):
    from ..services.dashboard import range_stats

    f_dt = datetime.combine(from_, datetime.min.time())
    t_dt = datetime.combine(to + timedelta(days=1), datetime.min.time())
    data = await range_stats(session, f_dt, t_dt)
    return TransactionStats(**data)


@router.get("/last", response_model=TransactionOut)
async def last(session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(select(Transaction).order_by(desc(Transaction.id)).limit(1))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "no transactions")
    return row


@router.get("/{tx_id}", response_model=TransactionOut)
async def get_tx(tx_id: int, session: AsyncSession = Depends(get_session)):
    tx = await session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "transaction not found")
    return tx


@router.post("", response_model=TransactionOut, status_code=201)
async def create_tx(data: TransactionCreate, session: AsyncSession = Depends(get_session)):
    payload = data.model_dump()
    ts = payload.get("ts")
    if ts is not None and ts.tzinfo is not None:
        payload["ts"] = ts.replace(tzinfo=None)
    tx = Transaction(**payload)
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


@router.patch("/{tx_id}", response_model=TransactionOut)
async def update_tx(
    tx_id: int, data: TransactionUpdate, session: AsyncSession = Depends(get_session)
):
    tx = await session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "transaction not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tx, k, v)
    await session.commit()
    await session.refresh(tx)
    return tx


@router.post("/{tx_id}/confirm", response_model=TransactionOut)
async def confirm_tx(tx_id: int, session: AsyncSession = Depends(get_session)):
    tx = await session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "transaction not found")
    tx.status = "confirmed"
    await session.commit()
    await session.refresh(tx)
    return tx


@router.post("/{tx_id}/reject", response_model=TransactionOut)
async def reject_tx(tx_id: int, session: AsyncSession = Depends(get_session)):
    tx = await session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "transaction not found")
    tx.status = "rejected"
    await session.commit()
    await session.refresh(tx)
    return tx


@router.delete("/{tx_id}", status_code=204)
async def delete_tx(tx_id: int, session: AsyncSession = Depends(get_session)):
    tx = await session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "transaction not found")
    await session.delete(tx)
    await session.commit()
    return None
