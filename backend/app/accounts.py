"""Règles d'accès : membres, invitations, sessions."""

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Invitation, Role, User, UserSession
from app.security import hash_password, hash_token, new_token, normalize_email, utcnow


class AccessError(Exception):
    """Erreur métier renvoyée telle quelle au client (message en français)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def count_members(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def count_pending_invitations(db: Session) -> int:
    stmt = (
        select(func.count())
        .select_from(Invitation)
        .where(Invitation.used_at.is_(None), Invitation.expires_at > utcnow())
    )
    return db.scalar(stmt) or 0


def create_user(
    db: Session, *, display_name: str, email: str, password: str, role: Role = Role.member
) -> User:
    if count_members(db) >= get_settings().max_members:
        raise AccessError("Le groupe est complet.", 409)
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AccessError("Un compte existe déjà avec cet email.", 409)
    user = User(
        display_name=display_name.strip(),
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def create_invitation(db: Session, created_by: User) -> tuple[Invitation, str]:
    """Crée une invitation ; renvoie aussi le jeton en clair, qui n'est stocké nulle part."""
    settings = get_settings()
    if count_members(db) + count_pending_invitations(db) >= settings.max_members:
        raise AccessError(
            f"{settings.max_members} membres maximum, invitations en attente comprises.", 409
        )
    token = new_token()
    invitation = Invitation(
        token_hash=hash_token(token),
        created_by_id=created_by.id,
        expires_at=utcnow() + timedelta(days=settings.invitation_days),
    )
    db.add(invitation)
    db.flush()
    return invitation, token


def get_valid_invitation(db: Session, token: str) -> Invitation:
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if invitation is None or invitation.used_at is not None or invitation.expires_at <= utcnow():
        raise AccessError("Lien d'invitation invalide ou expiré.", 404)
    return invitation


def accept_invitation(
    db: Session, token: str, *, display_name: str, email: str, password: str
) -> User:
    invitation = get_valid_invitation(db, token)
    user = create_user(db, display_name=display_name, email=email, password=password)
    invitation.used_at = utcnow()
    invitation.used_by_id = user.id
    return user


def open_session(db: Session, user: User) -> str:
    """Crée une session ; renvoie le jeton à mettre dans le cookie."""
    token = new_token()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=get_settings().session_days),
        )
    )
    db.flush()
    return token


def get_session_user(db: Session, token: str) -> User | None:
    stmt = select(UserSession).where(
        UserSession.token_hash == hash_token(token), UserSession.expires_at > utcnow()
    )
    session = db.scalar(stmt)
    return session.user if session else None


def close_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


def close_other_sessions(db: Session, user: User, keep_token: str) -> None:
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.token_hash != hash_token(keep_token)
        )
    )
