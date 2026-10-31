from fastapi import APIRouter, status

from app import accounts
from app.api.deps import AdminUser, DbSession
from app.schemas import InvitationOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def create_invitation(admin: AdminUser, db: DbSession) -> InvitationOut:
    invitation, token = accounts.create_invitation(db, created_by=admin)
    db.commit()
    # Le front construit le lien d'invitation à partir du jeton.
    return InvitationOut(token=token, expires_at=invitation.expires_at)
