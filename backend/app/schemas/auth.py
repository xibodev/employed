from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.users import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None


class RefreshTokenRequest(BaseModel):
    # Optional: browser clients send the refresh token via the httpOnly
    # cookie instead of the body (EMP-006).
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8)


class OAuthCallback(BaseModel):
    code: str
    state: str | None = None


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead | None = None
    message: str | None = None


class TokenStatusResponse(BaseModel):
    message: str
    verified_at: datetime | None = None
