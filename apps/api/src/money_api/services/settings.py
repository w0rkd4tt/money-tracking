from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AppSetting


async def get_or_create(session: AsyncSession) -> AppSetting:
    row = (await session.execute(select(AppSetting).where(AppSetting.id == 1))).scalar_one_or_none()
    if row is None:
        row = AppSetting(id=1)
        session.add(row)
        await session.flush()
    return row
