"""Shared helpers for matching LLM-emitted category strings against the
user's real category tree.

Used by both extract paths (chat and email) so a hallucinated path like
"Coffee shop" never sneaks past the LLM into the resolver, where the fuzzy
ladder might map it to a wrong row.

The canonical list is queried fresh per LLM call (in `_build_context` /
`build_context`) so the LLM always sees what the DB actually has — not a
stale snapshot.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category


def normalize_path(p: str) -> str:
    """Whitespace-collapse around the ` > ` separator and lowercase. Two
    paths normalise to the same value if they refer to the same node
    regardless of casing or stray whitespace."""
    parts = [seg.strip() for seg in (p or "").split(">")]
    return " > ".join(parts).lower()


async def load_user_categories(
    session: AsyncSession,
    *,
    kinds: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Read the user's categories from DB and return (paths, canonical_map).

    `paths` is the list to show the LLM (one path per line in the prompt).
    `canonical_map` is `normalize_path(p) → original_path` so callers can
    validate an LLM output and recover the canonical form.
    """
    q = select(Category.path).where(Category.path.isnot(None))
    if kinds:
        q = q.where(Category.kind.in_(kinds))
    rows = (await session.execute(q)).all()
    excl = set(exclude_paths or [])
    paths = [r.path for r in rows if r.path and r.path not in excl]
    canonical = {normalize_path(p): p for p in paths}
    return paths, canonical


def validate_llm_category(
    raw: str | None,
    canonical: dict[str, str],
) -> str | None:
    """Match an LLM-emitted category against the user's canonical list.

    Returns the canonical path (preserving the user's exact casing /
    spacing) or None if the LLM's output is empty / not in the list. None
    lets the caller fall through to the resolver's "Chưa phân loại"
    triage rather than fuzzy-matching to a wrong row.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    return canonical.get(normalize_path(s))
