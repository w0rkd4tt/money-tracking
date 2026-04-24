"""Admin endpoints: backup + restore helpers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services.backup import (
    list_backups,
    prune_backups,
    resolve_backup,
    run_backup,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class BackupOut(BaseModel):
    name: str
    path: str
    size_bytes: int
    created_at: datetime


class BackupResult(BaseModel):
    name: str
    size_bytes: int
    elapsed_ms: int


@router.post("/backup", response_model=BackupOut)
async def create_backup():
    import time

    t0 = time.perf_counter()
    try:
        b = await run_backup()
    except Exception as e:
        raise HTTPException(500, f"backup failed: {e}") from e
    _ = int((time.perf_counter() - t0) * 1000)
    return BackupOut(
        name=b.name, path=b.path, size_bytes=b.size_bytes, created_at=b.created_at
    )


@router.get("/backups", response_model=list[BackupOut])
async def list_all_backups():
    return [
        BackupOut(
            name=b.name, path=b.path, size_bytes=b.size_bytes, created_at=b.created_at
        )
        for b in list_backups()
    ]


@router.post("/backups/prune")
async def prune(days: int | None = None):
    removed = await prune_backups(days)
    return {"removed": removed}


@router.get("/backups/{name}")
async def download_backup(name: str):
    p = resolve_backup(name)
    if p is None:
        raise HTTPException(404, "backup not found")
    return FileResponse(
        path=str(p),
        media_type="application/octet-stream",
        filename=p.name,
    )
