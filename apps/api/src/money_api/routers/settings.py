from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..schemas.settings import SettingsOut, SettingsUpdate
from ..services.settings import get_or_create

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings_(session: AsyncSession = Depends(get_session)):
    return await get_or_create(session)


@router.patch("", response_model=SettingsOut)
async def update_settings(
    data: SettingsUpdate, session: AsyncSession = Depends(get_session)
):
    row = await get_or_create(session)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row
