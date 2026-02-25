"""User profile business logic."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_event
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.schemas.user import UpdateProfileRequest

logger = get_logger("user_service")


async def update_profile(
    db: AsyncSession, user_id: UUID, req: UpdateProfileRequest
) -> User:
    user = await db.get(User, user_id)

    if (
        req.display_name is None
        and req.email is None
        and req.new_password is None
    ):
        await db.refresh(user)
        return user

    if req.display_name is not None:
        user.display_name = req.display_name.strip()
        log_event(
            logger,
            "DISPLAY_NAME_CHANGED",
            user_id=str(user_id),
            metadata={"new_display_name": user.display_name},
        )

    if req.email is not None or req.new_password is not None:
        if not verify_password(req.current_password, user.hashed_password):
            log_event(logger, "WRONG_CURRENT_PASSWORD", user_id=str(user_id))
            raise HTTPException(401, "Current password is incorrect")

        if req.email is not None:
            new_email = req.email.strip().lower()
            existing = await db.execute(
                select(User).where(
                    User.email == new_email,
                    User.id != user_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(409, "Email already in use")
            user.email = new_email
            log_event(
                logger,
                "EMAIL_CHANGED",
                user_id=str(user_id),
                metadata={"new_email": new_email},
            )

        if req.new_password is not None:
            user.hashed_password = hash_password(req.new_password)
            log_event(
                logger,
                "PASSWORD_CHANGED",
                user_id=str(user_id),
                metadata={"field": "password"},
            )

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user
