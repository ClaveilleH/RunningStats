from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field
from pydantic_core import PydanticCustomError

from app.models import Role
from app.security import MIN_PASSWORD_LENGTH


def _check_password_length(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        # Message en français, affiché tel quel par le front.
        raise PydanticCustomError(
            "password_too_short",
            "Le mot de passe doit faire au moins {min_length} caractères.",
            {"min_length": MIN_PASSWORD_LENGTH},
        )
    return value


Password = Annotated[str, Field(max_length=200), AfterValidator(_check_password_length)]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class AcceptInvitationIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: Password


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: Password


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
    min_password_length: int


class InvitationOut(BaseModel):
    token: str
    expires_at: datetime
