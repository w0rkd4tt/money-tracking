from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Account, AllocationBucket, BucketAccount
from ..schemas.account import AccountCreate, AccountOut, AccountUpdate, BalanceOut
from ..services.balances import compute_balances

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Credit accounts auto-link to this bucket on creation. Match by name so the
# seed-default bucket "Trả nợ thẻ TD" picks it up. If a user renames or
# deletes the bucket, the auto-link is silently skipped — they can map
# manually via PATCH /buckets/{id}.
CREDIT_BUCKET_NAME = "Trả nợ thẻ TD"


async def _auto_link_credit_account(
    session: AsyncSession, account: Account
) -> None:
    if account.type != "credit":
        return
    bucket = (
        await session.execute(
            select(AllocationBucket).where(AllocationBucket.name == CREDIT_BUCKET_NAME)
        )
    ).scalar_one_or_none()
    if bucket is None:
        return
    # Skip if already linked (idempotent re-creates / patches)
    existing = (
        await session.execute(
            select(BucketAccount).where(
                BucketAccount.bucket_id == bucket.id,
                BucketAccount.account_id == account.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(BucketAccount(bucket_id=bucket.id, account_id=account.id))


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
):
    q = select(Account).order_by(Account.id)
    if not include_archived:
        q = q.where(Account.archived.is_(False))
    rows = (await session.execute(q)).scalars().all()
    return rows


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(data: AccountCreate, session: AsyncSession = Depends(get_session)):
    # If is_default=true → unset others
    if data.is_default:
        await _unset_other_defaults(session)
    acc = Account(**data.model_dump())
    session.add(acc)
    try:
        await session.flush()
    except Exception as e:
        await session.rollback()
        raise HTTPException(409, f"duplicate account name: {e}") from e
    await _auto_link_credit_account(session, acc)
    await session.commit()
    await session.refresh(acc)
    return acc


@router.get("/balance", response_model=list[BalanceOut])
async def balances(session: AsyncSession = Depends(get_session)):
    return await compute_balances(session)


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(account_id: int, session: AsyncSession = Depends(get_session)):
    acc = await session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    return acc


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int, data: AccountUpdate, session: AsyncSession = Depends(get_session)
):
    acc = await session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    patch = data.model_dump(exclude_unset=True)
    if patch.get("is_default"):
        await _unset_other_defaults(session, except_id=account_id)
    for k, v in patch.items():
        setattr(acc, k, v)
    await session.commit()
    await session.refresh(acc)
    return acc


@router.delete("/{account_id}", status_code=204)
async def archive_account(account_id: int, session: AsyncSession = Depends(get_session)):
    acc = await session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    acc.archived = True
    await session.commit()
    return None


async def _unset_other_defaults(session: AsyncSession, except_id: int | None = None) -> None:
    q = select(Account).where(Account.is_default.is_(True))
    rows = (await session.execute(q)).scalars().all()
    for r in rows:
        if except_id is not None and r.id == except_id:
            continue
        r.is_default = False
