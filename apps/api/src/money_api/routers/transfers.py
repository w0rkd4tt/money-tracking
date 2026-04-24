from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Transaction, TransferGroup
from ..schemas.transfer import TransferCreate, TransferOut
from ..services.transfers import TransferError, create_transfer, delete_transfer

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("", response_model=list[TransferOut])
async def list_transfers(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(select(TransferGroup).order_by(desc(TransferGroup.ts)).limit(limit))
    ).scalars().all()
    out: list[TransferOut] = []
    for tg in rows:
        tx_ids = (
            await session.execute(
                select(Transaction.id).where(Transaction.transfer_group_id == tg.id)
            )
        ).scalars().all()
        out.append(
            TransferOut(
                id=tg.id,
                ts=tg.ts,
                from_account_id=tg.from_account_id,
                to_account_id=tg.to_account_id,
                amount=tg.amount,
                fee=tg.fee,
                currency=tg.currency,
                fx_rate=tg.fx_rate,
                note=tg.note,
                source=tg.source,
                created_at=tg.created_at,
                transaction_ids=list(tx_ids),
            )
        )
    return out


@router.post("", response_model=TransferOut, status_code=201)
async def create(data: TransferCreate, session: AsyncSession = Depends(get_session)):
    try:
        result = await create_transfer(session, data)
        await session.commit()
        return result
    except TransferError as e:
        await session.rollback()
        raise HTTPException(400, str(e)) from e


@router.delete("/{transfer_id}", status_code=204)
async def delete(transfer_id: int, session: AsyncSession = Depends(get_session)):
    try:
        await delete_transfer(session, transfer_id)
        await session.commit()
    except TransferError as e:
        await session.rollback()
        raise HTTPException(404, str(e)) from e
