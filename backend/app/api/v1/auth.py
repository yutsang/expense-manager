"""Auth API — signup, login, logout, token refresh."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    AuthUserResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from app.core.db import AsyncSessionLocal
from app.services.auth import AuthError, UserAlreadyExistsError, login, logout, refresh, signup

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_ACCESS = "aegis_access"
_COOKIE_REFRESH = "aegis_refresh"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days in seconds


async def _get_plain_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


PlainDb = Annotated[AsyncSession, Depends(_get_plain_db)]


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=_COOKIE_ACCESS,
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 15,  # 15 minutes — matches JWT expiry
    )
    response.set_cookie(
        key=_COOKIE_REFRESH,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=_COOKIE_MAX_AGE,
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def do_signup(body: SignupRequest, response: Response, db: PlainDb) -> SignupResponse:
    try:
        user, tenant, access_token, refresh_token = await signup(
            db,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            tenant_name=body.tenant_name,
            country=body.country,
            currency=body.currency,
        )
        await db.commit()
    except UserAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))

    _set_auth_cookies(response, access_token, refresh_token)
    return SignupResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
        ),
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def do_login(body: LoginRequest, response: Response, db: PlainDb) -> LoginResponse:
    try:
        user, access_token, refresh_token, tenant_ids = await login(
            db,
            email=body.email,
            password=body.password,
        )
        await db.commit()
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
        ),
        tenant_ids=tenant_ids,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def do_logout(
    response: Response,
    db: PlainDb,
    # Accept refresh token from cookie or body for flexibility
    refresh_token: str | None = None,
) -> None:
    if refresh_token:
        # Best-effort revocation — don't expose whether token was valid
        try:
            # We don't have user_id here; scan by token hash
            from sqlalchemy import select as _select

            from app.infra.models import Session as _Session
            from app.services.auth import _hash_token as _ht

            token_hash = _ht(refresh_token)
            session_row = await db.scalar(
                _select(_Session).where(_Session.refresh_token_hash == token_hash)
            )
            if session_row is not None:
                await logout(db, user_id=session_row.user_id, refresh_token_raw=refresh_token)
                await db.commit()
        except Exception:  # noqa: BLE001, S110 — intentional catch-all for logout
            pass

    response.delete_cookie(_COOKIE_ACCESS)
    response.delete_cookie(_COOKIE_REFRESH)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def do_refresh(
    response: Response,
    db: PlainDb,
    refresh_token: str,
) -> TokenResponse:
    try:
        access_token, new_refresh_token = await refresh(db, refresh_token_raw=refresh_token)
        await db.commit()
    except AuthError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid or expired"
        )

    _set_auth_cookies(response, access_token, new_refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)
