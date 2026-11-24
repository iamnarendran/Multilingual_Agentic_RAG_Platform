from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, ServicesDep
from app.db import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: DbDep, services: ServicesDep) -> TokenResponse:
    email = body.email.lower()
    exists = await session.scalar(select(User.id).where(func.lower(User.email) == email))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(email=email, name=body.name, password_hash=hash_password(body.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # concurrent sign-up with the same email
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from None
    return TokenResponse(
        access_token=create_access_token(user.id, services.settings), user=UserOut.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: DbDep, services: ServicesDep) -> TokenResponse:
    user = await session.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return TokenResponse(
        access_token=create_access_token(user.id, services.settings), user=UserOut.model_validate(user)
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
