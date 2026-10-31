from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app import accounts
from app.api.deps import DbSession, clear_session_cookie, session_token, set_session_cookie
from app.models import User
from app.schemas import AcceptInvitationIn, InvitationCheckOut, LoginIn, MeOut
from app.security import normalize_email, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, db: DbSession) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if not verify_password(user.password_hash if user else None, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect.")
    assert user is not None
    set_session_cookie(response, accounts.open_session(db, user))
    db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    token = session_token(request)
    if token:
        accounts.close_session(db, token)
        db.commit()
    clear_session_cookie(response)


@router.get("/invitations/{token}", response_model=InvitationCheckOut)
def check_invitation(token: str, db: DbSession) -> InvitationCheckOut:
    invitation = accounts.get_valid_invitation(db, token)
    return InvitationCheckOut(valid=True, expires_at=invitation.expires_at)


@router.post("/invitations/{token}", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def accept_invitation(
    token: str, body: AcceptInvitationIn, response: Response, db: DbSession
) -> User:
    user = accounts.accept_invitation(
        db, token, display_name=body.display_name, email=body.email, password=body.password
    )
    # Le nouveau membre est connecté directement.
    set_session_cookie(response, accounts.open_session(db, user))
    db.commit()
    return user
