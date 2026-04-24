"""Langfuse callback handler — optional, graceful when keys missing."""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


def get_langfuse_callbacks() -> list[Any]:
    s = get_settings()
    if not s.langfuse_enabled:
        return []
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        log.warning("Langfuse enabled but keys missing; tracing disabled")
        return []
    try:
        from langfuse.callback import CallbackHandler  # type: ignore
    except ImportError:
        log.warning("langfuse package not installed; tracing disabled")
        return []

    try:
        handler = CallbackHandler(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
        return [handler]
    except Exception as e:  # pragma: no cover
        log.warning("Langfuse init failed: %s", e)
        return []
