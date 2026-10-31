from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.accounts import get_session_user
from app.config import get_settings
from app.db import get_db
from app.models import Role, User

DbSession = Annotated[Session, Depends(get_db)]


def session_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def current_user(request: Request, db: DbSession) -> User:
    token = session_token(request)
    user = get_session_user(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion requise.")
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'admin.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(admin_user)]


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(get_settings().session_cookie_name, path="/")
