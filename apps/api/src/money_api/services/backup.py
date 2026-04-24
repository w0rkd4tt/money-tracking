"""Postgres backup via pg_dump + prune + list.

Writes custom-format dumps to `/app/backups/` (mounted from `./backups` on
host). Custom format is compact and restores with `pg_restore`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from ..config import get_settings

log = logging.getLogger(__name__)

BACKUP_DIR = Path("/app/backups")
FILE_PREFIX = "money-"
FILE_SUFFIX = ".dump"


@dataclass
class BackupFile:
    name: str
    path: str
    size_bytes: int
    created_at: datetime


def _sync_db_url() -> str:
    """Return a libpq-compatible URL (strip async driver markers)."""
    raw = get_settings().database_url
    return raw.replace("+asyncpg", "").replace("+psycopg", "")


def _parse_libpq_env(url: str) -> dict[str, str]:
    """Turn a postgres:// URL into PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE
    so pg_dump can be invoked without exposing the password on the command line.
    """
    u = urlparse(url)
    env = os.environ.copy()
    if u.hostname:
        env["PGHOST"] = u.hostname
    if u.port:
        env["PGPORT"] = str(u.port)
    if u.username:
        env["PGUSER"] = u.username
    if u.password:
        env["PGPASSWORD"] = u.password
    if u.path and len(u.path) > 1:
        env["PGDATABASE"] = u.path.lstrip("/")
    return env


async def run_backup() -> BackupFile:
    """Dump DB to a timestamped file. Returns metadata."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = BACKUP_DIR / f"{FILE_PREFIX}{ts}{FILE_SUFFIX}"
    url = _sync_db_url()
    env = _parse_libpq_env(url)

    cmd = [
        "pg_dump",
        "--format=custom",
        "--compress=9",
        "--file", str(out),
        env.get("PGDATABASE", ""),  # positional = dbname
    ]
    log.info("pg_dump → %s", out)
    start = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"pg_dump exit {proc.returncode}: {stderr.decode('utf-8', errors='replace')}"
        )
    elapsed = time.perf_counter() - start
    size = out.stat().st_size
    log.info("backup done: %s (%.1f KB, %.1fs)", out.name, size / 1024, elapsed)
    return BackupFile(
        name=out.name,
        path=str(out),
        size_bytes=size,
        created_at=datetime.fromtimestamp(out.stat().st_mtime),
    )


async def prune_backups(retention_days: int | None = None) -> int:
    if not BACKUP_DIR.exists():
        return 0
    days = retention_days if retention_days is not None else get_settings().backup_retention_days
    cutoff = time.time() - days * 86_400
    removed = 0
    for f in BACKUP_DIR.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}"):
        if f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                removed += 1
                log.info("pruned old backup: %s", f.name)
            except Exception as e:
                log.warning("prune failed for %s: %s", f.name, e)
    return removed


def list_backups() -> list[BackupFile]:
    if not BACKUP_DIR.exists():
        return []
    items: list[BackupFile] = []
    for f in BACKUP_DIR.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}"):
        st = f.stat()
        items.append(
            BackupFile(
                name=f.name,
                path=str(f),
                size_bytes=st.st_size,
                created_at=datetime.fromtimestamp(st.st_mtime),
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items


_FILENAME_RE = re.compile(rf"^{re.escape(FILE_PREFIX)}[\w\-]+{re.escape(FILE_SUFFIX)}$")


def resolve_backup(name: str) -> Path | None:
    """Return the backup path only if `name` matches our safe pattern and
    resolves inside BACKUP_DIR (block path traversal)."""
    if not _FILENAME_RE.match(name):
        return None
    p = (BACKUP_DIR / name).resolve()
    try:
        p.relative_to(BACKUP_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None
