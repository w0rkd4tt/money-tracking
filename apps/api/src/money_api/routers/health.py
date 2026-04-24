from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..llm.provider import resolve_provider

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    provider = await resolve_provider(session)
    llm_ok = await provider.ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "llm": "ok" if llm_ok else "unreachable",
        "llm_provider": provider.name,
        "llm_url": provider.chat_endpoint,
        "llm_model": provider.model,
    }


@router.get("/info")
async def info():
    from .. import __version__

    s = get_settings()
    return {
        "version": __version__,
        "env": s.app_env,
        "timezone": s.tz,
        "currency": s.default_currency,
        "gmail_target": s.gmail_target_email,
    }
