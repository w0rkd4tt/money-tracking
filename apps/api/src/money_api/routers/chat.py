from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..llm.chat_service import process_chat
from ..schemas.chat import ChatMessageRequest, ChatMessageResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    req: ChatMessageRequest, session: AsyncSession = Depends(get_session)
):
    resp = await process_chat(session, req)
    await session.commit()
    return resp
