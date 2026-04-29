from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Account, AllocationBucket, Category
from ..schemas.bucket import BucketCreate, BucketOut, BucketUpdate
from ..services.buckets import (
    bucket_out_dict,
    set_bucket_accounts,
    set_bucket_categories,
)

router = APIRouter(prefix="/buckets", tags=["buckets"])


async def _validate_categories(session: AsyncSession, ids: list[int]) -> None:
    if not ids:
        return
    rows = (await session.execute(select(Category).where(Category.id.in_(ids)))).scalars().all()
    found = {c.id for c in rows}
    missing = set(ids) - found
    if missing:
        raise HTTPException(400, f"category not found: {sorted(missing)}")
    bad_kind = [c for c in rows if c.kind != "expense"]
    if bad_kind:
        raise HTTPException(
            400,
            f"only expense categories can be bucketed: {[c.name for c in bad_kind]}",
        )


async def _validate_accounts(session: AsyncSession, ids: list[int]) -> None:
    if not ids:
        return
    rows = (await session.execute(select(Account).where(Account.id.in_(ids)))).scalars().all()
    found = {a.id for a in rows}
    missing = set(ids) - found
    if missing:
        raise HTTPException(400, f"account not found: {sorted(missing)}")


@router.get("", response_model=list[BucketOut])
async def list_buckets(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
):
    q = select(AllocationBucket).order_by(AllocationBucket.sort_order, AllocationBucket.id)
    if not include_archived:
        q = q.where(AllocationBucket.archived.is_(False))
    buckets = (await session.execute(q)).scalars().all()
    return [await bucket_out_dict(session, b) for b in buckets]


@router.post("", response_model=BucketOut, status_code=201)
async def create_bucket(data: BucketCreate, session: AsyncSession = Depends(get_session)):
    await _validate_categories(session, data.category_ids)
    await _validate_accounts(session, data.account_ids)
    b = AllocationBucket(
        name=data.name,
        icon=data.icon,
        color=data.color,
        sort_order=data.sort_order,
        note=data.note,
    )
    session.add(b)
    try:
        await session.flush()
    except Exception as e:
        await session.rollback()
        raise HTTPException(409, f"duplicate bucket name: {e}") from e
    await set_bucket_categories(session, b.id, data.category_ids)
    await set_bucket_accounts(session, b.id, data.account_ids)
    await session.commit()
    await session.refresh(b)
    return await bucket_out_dict(session, b)


@router.get("/{bucket_id}", response_model=BucketOut)
async def get_bucket(bucket_id: int, session: AsyncSession = Depends(get_session)):
    b = await session.get(AllocationBucket, bucket_id)
    if not b:
        raise HTTPException(404, "bucket not found")
    return await bucket_out_dict(session, b)


@router.patch("/{bucket_id}", response_model=BucketOut)
async def update_bucket(
    bucket_id: int,
    data: BucketUpdate,
    session: AsyncSession = Depends(get_session),
):
    b = await session.get(AllocationBucket, bucket_id)
    if not b:
        raise HTTPException(404, "bucket not found")
    patch = data.model_dump(exclude_unset=True)
    category_ids = patch.pop("category_ids", None)
    account_ids = patch.pop("account_ids", None)
    for k, v in patch.items():
        setattr(b, k, v)
    if category_ids is not None:
        await _validate_categories(session, category_ids)
        await set_bucket_categories(session, b.id, category_ids)
    if account_ids is not None:
        await _validate_accounts(session, account_ids)
        await set_bucket_accounts(session, b.id, account_ids)
    await session.commit()
    await session.refresh(b)
    return await bucket_out_dict(session, b)


@router.delete("/{bucket_id}", status_code=204)
async def delete_bucket(bucket_id: int, session: AsyncSession = Depends(get_session)):
    b = await session.get(AllocationBucket, bucket_id)
    if not b:
        raise HTTPException(404, "bucket not found")
    await session.delete(b)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(409, f"cannot delete bucket (in use): {e}") from e
    return None
