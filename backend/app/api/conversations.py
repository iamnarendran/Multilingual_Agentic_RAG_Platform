from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep
from app.db import Conversation
from app.schemas import ConversationDetail, ConversationOut, ConversationUpdate

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def get_owned_conversation(
    session: DbDep, user_id: str, conversation_id: str, *, with_messages: bool = False
) -> Conversation:
    stmt = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    if with_messages:
        stmt = stmt.options(selectinload(Conversation.messages))
    conv = await session.scalar(stmt)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser, session: DbDep) -> list[Conversation]:
    result = await session.scalars(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(200)
    )
    return list(result)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user: CurrentUser, session: DbDep) -> Conversation:
    return await get_owned_conversation(session, user.id, conversation_id, with_messages=True)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: str, body: ConversationUpdate, user: CurrentUser, session: DbDep
) -> Conversation:
    conv = await get_owned_conversation(session, user.id, conversation_id)
    conv.title = body.title.strip()
    await session.commit()
    return conv


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser, session: DbDep) -> None:
    conv = await get_owned_conversation(session, user.id, conversation_id, with_messages=True)
    await session.delete(conv)
    await session.commit()
