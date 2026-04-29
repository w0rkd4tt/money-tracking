from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Account, Category, Transaction, TransferGroup
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


class LinkCreditPaymentRequest(BaseModel):
    credit_account_id: int


class LinkCreditPaymentResponse(BaseModel):
    transfer_group_id: int
    source_tx_id: int
    credit_leg_tx_id: int


@router.post("/{tx_id}/link-credit-payment", response_model=LinkCreditPaymentResponse)
async def link_credit_payment(
    tx_id: int,
    data: LinkCreditPaymentRequest,
    session: AsyncSession = Depends(get_session),
):
    """Convert a single-leg credit-card-payment tx into a proper transfer pair.

    Use case: a Timo "vừa giảm 4M, Mô tả: Tra no tin dung HSBC" arrives. The
    poller records -4M on Timo (kind=expense, category="Thanh toán thẻ TD").
    The HSBC side won't appear in our DB until HSBC's own email arrives
    days later — meanwhile HSBC's debt display stays stale.

    This endpoint lets the user bind the source tx to a credit account NOW:
      1. Creates a TransferGroup (Timo → HSBC, amount=4M)
      2. Source tx kind flips expense → transfer; transfer_group_id set
      3. Sibling +4M income tx created on the credit account, status=
         confirmed, source=`manual:cc-payment`, also in the same group

    Result: HSBC debt drops by 4M immediately. When HSBC's confirming email
    finally arrives, the gmail poller will detect the matching TransferGroup
    leg and skip duplicating.
    """
    source = await session.get(Transaction, tx_id)
    if source is None:
        raise HTTPException(404, "source transaction not found")
    if source.transfer_group_id is not None:
        raise HTTPException(409, "tx is already part of a transfer group")
    if source.amount >= 0:
        raise HTTPException(
            400, "expected an outgoing (negative) tx for a credit-card payment"
        )

    credit_acct = await session.get(Account, data.credit_account_id)
    if credit_acct is None:
        raise HTTPException(404, "credit account not found")
    if credit_acct.type != "credit":
        raise HTTPException(
            400, f"account '{credit_acct.name}' is not a credit account"
        )
    if credit_acct.id == source.account_id:
        raise HTTPException(400, "destination must differ from source account")

    abs_amount: Decimal = -source.amount  # positive magnitude

    # Build the transfer group.
    group = TransferGroup(
        ts=source.ts,
        from_account_id=source.account_id,
        to_account_id=credit_acct.id,
        amount=abs_amount,
        currency=source.currency,
        note="Credit-card payment (linked from email-ingested tx)",
        source="manual:cc-payment",
    )
    session.add(group)
    await session.flush()

    # Promote source tx into the transfer (Transaction has no `kind` column —
    # transfer-ness is implied by `transfer_group_id` being set).
    source.transfer_group_id = group.id

    # Resolve "Thanh toán thẻ TD" category for the credit-leg (income on the
    # credit account = debt reduction). Falls back to source's category.
    pay_cat = (
        await session.execute(
            select(Category).where(Category.path.ilike("%Thanh toán thẻ TD%")).limit(1)
        )
    ).scalar_one_or_none()
    leg_category_id = pay_cat.id if pay_cat else source.category_id

    leg = Transaction(
        ts=source.ts,
        amount=abs_amount,  # POSITIVE on credit account → reduces debt
        currency=source.currency,
        account_id=credit_acct.id,
        category_id=leg_category_id,
        merchant_text=source.merchant_text,
        note=f"Credit-card payment from acct #{source.account_id}",
        source="manual:cc-payment",
        confidence=1.0,
        status="confirmed",
        transfer_group_id=group.id,
    )
    session.add(leg)
    await session.flush()
    await session.commit()
    return LinkCreditPaymentResponse(
        transfer_group_id=group.id,
        source_tx_id=source.id,
        credit_leg_tx_id=leg.id,
    )
