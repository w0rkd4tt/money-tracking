from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, Category, Transaction, TransferGroup
from ..schemas.transfer import TransferCreate, TransferOut


class TransferError(ValueError):
    pass


async def _get_transfer_category(session: AsyncSession) -> int:
    result = await session.execute(
        select(Category.id).where(Category.kind == "transfer", Category.parent_id.is_(None))
    )
    row = result.first()
    if row:
        return row[0]
    cat = Category(name="Transfer", kind="transfer", path="Transfer")
    session.add(cat)
    await session.flush()
    return cat.id


async def create_transfer(
    session: AsyncSession,
    data: TransferCreate,
    *,
    source: str = "manual",
) -> TransferOut:
    if data.from_account_id == data.to_account_id:
        raise TransferError("from_account and to_account must differ")

    from_acct = await session.get(Account, data.from_account_id)
    to_acct = await session.get(Account, data.to_account_id)
    if not from_acct or not to_acct:
        raise TransferError("account not found")

    ts_naive = data.ts.replace(tzinfo=None) if data.ts.tzinfo else data.ts

    tg = TransferGroup(
        ts=ts_naive,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        amount=data.amount,
        fee=data.fee,
        currency=data.currency,
        fx_rate=data.fx_rate,
        note=data.note,
        source=source,
    )
    session.add(tg)
    await session.flush()

    transfer_cat = await _get_transfer_category(session)

    fx = data.fx_rate or Decimal("1")
    debit = Transaction(
        ts=ts_naive,
        amount=-(data.amount + data.fee),
        currency=data.currency,
        account_id=data.from_account_id,
        category_id=transfer_cat,
        merchant_text=f"→ {to_acct.name}",
        note=data.note,
        source=source,
        confidence=1.0,
        status="confirmed",
        transfer_group_id=tg.id,
    )
    credit = Transaction(
        ts=ts_naive,
        amount=data.amount * fx,
        currency=to_acct.currency,
        account_id=data.to_account_id,
        category_id=transfer_cat,
        merchant_text=f"← {from_acct.name}",
        note=data.note,
        source=source,
        confidence=1.0,
        status="confirmed",
        transfer_group_id=tg.id,
    )
    session.add_all([debit, credit])
    await session.flush()

    return TransferOut(
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
        transaction_ids=[debit.id, credit.id],
    )


async def delete_transfer(session: AsyncSession, transfer_id: int) -> None:
    tg = await session.get(TransferGroup, transfer_id)
    if not tg:
        raise TransferError("transfer not found")
    await session.execute(
        delete(Transaction).where(Transaction.transfer_group_id == transfer_id)
    )
    await session.delete(tg)
