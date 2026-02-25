"""User-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


def validate_password_strength(v: str) -> str:
    """Reusable validator. Raises ValueError with descriptive message."""
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit")
    return v


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def no_whitespace_only(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError("display_name cannot be whitespace only")
        return v.strip() if v else v

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if v is not None:
            return validate_password_strength(v)
        return v

    @model_validator(mode="after")
    def passwords_require_current(self):
        if self.email is not None and self.current_password is None:
            raise ValueError("current_password required when changing email")
        if self.new_password is not None and self.current_password is None:
            raise ValueError("current_password required when changing password")
        if (
            self.new_password is not None
            and self.current_password is not None
            and self.new_password == self.current_password
        ):
            raise ValueError("new_password must differ from current_password")
        return self
