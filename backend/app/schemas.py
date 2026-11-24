"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth --------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: str
    email: str
    name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Documents ---------------------------------------------------------------


class DocumentOut(ORM):
    id: str
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    error: str | None
    language: str | None
    page_count: int | None
    chunk_count: int
    ocr_pages: int
    warnings: list[str] | None
    created_at: datetime


# --- Conversations -----------------------------------------------------------


class MessageOut(ORM):
    id: str
    role: str
    content: str
    language: str | None
    query_type: str | None
    sources: list[dict[str, Any]] | None
    trace: list[dict[str, Any]] | None
    validation: dict[str, Any] | None
    usage: dict[str, Any] | None
    status: str
    created_at: datetime


class ConversationOut(ORM):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


# --- Chat --------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=100)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v.strip()
