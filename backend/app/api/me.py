from fastapi import APIRouter, HTTPException, Request, status

from app import accounts
from app.api.deps import CurrentUser, DbSession, session_token
from app.models import User
from app.schemas import ChangePasswordIn, MeOut
from app.security import hash_password, verify_password

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
def me(user: CurrentUser) -> User:
    return user


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordIn, request: Request, user: CurrentUser, db: DbSession
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect.")
    user.password_hash = hash_password(body.new_password)
    # Les autres appareils sont déconnectés ; la session en cours reste ouverte.
    token = session_token(request)
    assert token is not None
    accounts.close_other_sessions(db, user, keep_token=token)
    db.commit()
