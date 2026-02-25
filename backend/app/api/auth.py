"""Auth API router."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from app.services.auth_service import (
    is_refresh_token_revoked,
    login,
    refresh_tokens,
    revoke_refresh_token,
    signup,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
@limiter.exempt
async def signup_endpoint(data: SignupRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await signup(db, data)
        await db.commit()
        return SignupResponse(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
        )
    except ValueError as e:
        if str(e) == "EMAIL_EXISTS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        raise


@router.post("/login", response_model=TokenResponse)
@limiter.exempt
async def login_endpoint(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, access_token, refresh_token = await login(db, data.email, data.password)
        await db.commit()
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except ValueError as e:
        if str(e) == "USER_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if str(e) == "BAD_PASSWORD":
            # Per-email rate limit for failed logins (5/minute)
            from app.services.auth_service import check_login_rate_limit
            if check_login_rate_limit(data.email):
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        raise


@router.post("/logout")
async def logout_endpoint(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
):
    revoke_refresh_token(body.refresh_token)
    return {"message": "Logged out"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(body: RefreshRequest):
    try:
        access_token, new_refresh_token = refresh_tokens(body.refresh_token)
        return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)
    except ValueError as e:
        if str(e) == "TOKEN_REVOKED":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
