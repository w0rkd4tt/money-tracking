from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AllocationBucket, BucketCategory


async def category_ids_for(session: AsyncSession, bucket_id: int) -> list[int]:
    rows = (
        await session.execute(
            select(BucketCategory.category_id).where(BucketCategory.bucket_id == bucket_id)
        )
    ).all()
    return [r[0] for r in rows]


async def set_bucket_categories(
    session: AsyncSession, bucket_id: int, category_ids: list[int]
) -> None:
    """Replace the full mapping for a bucket. Enforces 1 category → 1 bucket."""
    existing = {
        r[0]
        for r in (
            await session.execute(
                select(BucketCategory.category_id).where(BucketCategory.bucket_id == bucket_id)
            )
        ).all()
    }
    wanted = set(category_ids)
    to_add = wanted - existing
    to_del = existing - wanted

    for cid in to_add:
        # steal from any other bucket (1 cat = 1 bucket)
        await session.execute(
            BucketCategory.__table__.delete().where(
                BucketCategory.category_id == cid,
                BucketCategory.bucket_id != bucket_id,
            )
        )
        session.add(BucketCategory(bucket_id=bucket_id, category_id=cid))

    if to_del:
        await session.execute(
            BucketCategory.__table__.delete().where(
                BucketCategory.bucket_id == bucket_id,
                BucketCategory.category_id.in_(to_del),
            )
        )


async def bucket_out_dict(session: AsyncSession, bucket: AllocationBucket) -> dict:
    cats = await category_ids_for(session, bucket.id)
    return {
        "id": bucket.id,
        "name": bucket.name,
        "icon": bucket.icon,
        "color": bucket.color,
        "sort_order": bucket.sort_order,
        "archived": bucket.archived,
        "note": bucket.note,
        "category_ids": cats,
    }
