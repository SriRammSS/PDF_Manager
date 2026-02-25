"""Users API router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.logging import get_logger, log_event
from app.db.models import User
from app.db.session import get_db
from app.schemas.user import UpdateProfileRequest, UserResponse
from app.services.user_service import update_profile

router = APIRouter(prefix="/users", tags=["users"])
logger = get_logger("api.users")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    log_event(logger, "PROFILE_FETCHED", user_id=str(current_user.id))
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def patch_me(
    body: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    log_event(logger, "PROFILE_UPDATE_REQUEST", user_id=str(current_user.id))
    user = await update_profile(db, current_user.id, body)
    return UserResponse.model_validate(user)
