from __future__ import annotations

import hashlib
import json
import time
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LlmToolCallLog


@asynccontextmanager
async def record(
    session: AsyncSession,
    session_id: int | None,
    turn_index: int,
    tool_name: str,
    params: dict[str, Any],
    trace_id: str | None = None,
):
    start = time.perf_counter()
    raw = json.dumps(params, sort_keys=True, default=str).encode()
    h = hashlib.sha256(raw).hexdigest()
    entry = LlmToolCallLog(
        session_id=session_id,
        turn_index=turn_index,
        tool_name=tool_name,
        params_json=params,
        input_hash=h,
        status="ok",
        trace_id=trace_id,
    )
    session.add(entry)
    try:
        yield entry
        entry.status = entry.status or "ok"
    except Exception as e:
        entry.status = "error"
        entry.error = str(e)[:1000]
        raise
    finally:
        entry.duration_ms = int((time.perf_counter() - start) * 1000)
        await session.flush()
