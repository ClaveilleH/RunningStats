from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role
from app.security import MIN_PASSWORD_LENGTH

Password = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class AcceptInvitationIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Password


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Password


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    username: str | None
    email: str
    role: Role
    theme: str


class InvitationCheckOut(BaseModel):
    valid: bool
    expires_at: datetime


class InvitationOut(BaseModel):
    token: str
    expires_at: datetime
