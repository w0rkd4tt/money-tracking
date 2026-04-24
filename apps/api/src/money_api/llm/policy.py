"""Gmail allowlist/denylist enforcement for LLM tools.

Policy evaluated in-process; decisions never rely on prompt text.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LlmGmailPolicy


@dataclass
class PolicyDecision:
    allowed: bool
    rewritten_query: str | None
    matched_allows: list[int]
    matched_denies: list[int]
    reason: str


def _to_gmail_clause(pattern_type: str, pattern: str) -> str:
    """Convert a stored policy pattern into Gmail search clause.

    Supported: from, to, label, subject, query (raw).
    """
    p = pattern.strip()
    if pattern_type == "query":
        return f"({p})"
    if pattern_type == "from":
        return f"from:{p}"
    if pattern_type == "to":
        return f"to:{p}"
    if pattern_type == "label":
        return f"label:{p}"
    if pattern_type == "subject":
        return f"subject:{p}"
    return f"({p})"


async def evaluate(session: AsyncSession, user_query: str) -> PolicyDecision:
    rows = (
        await session.execute(
            select(LlmGmailPolicy)
            .where(LlmGmailPolicy.enabled.is_(True))
            .order_by(LlmGmailPolicy.priority.desc())
        )
    ).scalars().all()

    allows = [r for r in rows if r.action == "allow"]
    denies = [r for r in rows if r.action == "deny"]

    if not allows:
        return PolicyDecision(
            allowed=False,
            rewritten_query=None,
            matched_allows=[],
            matched_denies=[],
            reason="No enabled allow policy. LLM access to Gmail is denied by default.",
        )

    allow_clause = " OR ".join(_to_gmail_clause(r.pattern_type, r.pattern) for r in allows)
    deny_clause = " ".join(
        "-" + _to_gmail_clause(r.pattern_type, r.pattern) for r in denies
    )

    # User query may be empty → still return just the allowlist-scoped query
    user_part = f"({user_query})" if user_query else ""
    parts = [f"({allow_clause})"]
    if deny_clause:
        parts.append(deny_clause)
    if user_part:
        parts.append(user_part)
    rewritten = " ".join(parts)

    return PolicyDecision(
        allowed=True,
        rewritten_query=rewritten,
        matched_allows=[r.id for r in allows],
        matched_denies=[r.id for r in denies],
        reason="OK",
    )
