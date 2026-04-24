from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..llm.policy import evaluate
from ..models import LlmGmailPolicy, LlmToolCallLog
from ..schemas.llm import (
    GmailPolicyCreate,
    GmailPolicyOut,
    GmailPolicyTestRequest,
    GmailPolicyTestResponse,
    LlmAuditOut,
)

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/policies/gmail", response_model=list[GmailPolicyOut])
async def list_policies(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(LlmGmailPolicy).order_by(LlmGmailPolicy.priority.desc(), LlmGmailPolicy.id)
        )
    ).scalars().all()
    return rows


@router.post("/policies/gmail", response_model=GmailPolicyOut, status_code=201)
async def create_policy(
    data: GmailPolicyCreate, session: AsyncSession = Depends(get_session)
):
    row = LlmGmailPolicy(**data.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/policies/gmail/{policy_id}", response_model=GmailPolicyOut)
async def update_policy(
    policy_id: int,
    data: GmailPolicyCreate,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(LlmGmailPolicy, policy_id)
    if not row:
        raise HTTPException(404, "policy not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/policies/gmail/{policy_id}", status_code=204)
async def delete_policy(policy_id: int, session: AsyncSession = Depends(get_session)):
    row = await session.get(LlmGmailPolicy, policy_id)
    if not row:
        raise HTTPException(404, "policy not found")
    await session.delete(row)
    await session.commit()
    return None


@router.post("/policies/gmail/test", response_model=GmailPolicyTestResponse)
async def test_policy(
    req: GmailPolicyTestRequest, session: AsyncSession = Depends(get_session)
):
    decision = await evaluate(session, req.query)
    return GmailPolicyTestResponse(
        allowed=decision.allowed,
        rewritten_query=decision.rewritten_query,
        matched_allows=decision.matched_allows,
        matched_denies=decision.matched_denies,
        reason=decision.reason,
    )


@router.get("/audit", response_model=list[LlmAuditOut])
async def audit(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(LlmToolCallLog).order_by(LlmToolCallLog.id.desc()).limit(limit)
        )
    ).scalars().all()
    return rows
