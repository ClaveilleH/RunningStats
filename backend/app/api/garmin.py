from datetime import UTC, datetime, time

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app import crypto, garmin
from app.api.deps import CurrentUser, DbSession
from app.models import GarminAccount, GarminSource, GarminStatus
from app.schemas import GarminKeyIn, GarminOut

router = APIRouter(prefix="/me/garmin", tags=["garmin"])


def _out(account: GarminAccount | None) -> GarminOut:
    if account is None:
        return GarminOut(connected=False)
    return GarminOut(
        connected=True,
        source=account.source,
        status=account.status,
        api_key_expires_at=account.api_key_expires_at,
        key_expires_soon=garmin.key_expires_soon(account),
        last_sync_at=account.last_sync_at,
        last_error=account.last_error,
    )


@router.get("", response_model=GarminOut)
def get_garmin(user: CurrentUser, db: DbSession) -> GarminOut:
    account = db.scalar(select(GarminAccount).where(GarminAccount.user_id == user.id))
    return _out(account)


@router.put("", response_model=GarminOut)
def set_garmin_key(body: GarminKeyIn, user: CurrentUser, db: DbSession) -> GarminOut:
    """Enregistre une clé personnelle après l'avoir testée auprès de Garmin."""
    api_key = body.api_key.strip()
    try:
        token, token_expires_at = garmin.exchange_key(api_key)
    except garmin.GarminKeyRejected as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Garmin a refusé cette clé. Vérifie-la ou crées-en une."
        ) from e
    except garmin.GarminUnavailable as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Garmin ne répond pas, réessaie dans un moment."
        ) from e

    account = db.scalar(select(GarminAccount).where(GarminAccount.user_id == user.id))
    if account is None:
        account = GarminAccount(user_id=user.id)
        db.add(account)
    account.source = GarminSource.personal_api
    account.api_key_encrypted = crypto.encrypt(api_key)
    account.api_key_expires_at = (
        datetime.combine(body.api_key_expires_on, time.max, tzinfo=UTC)
        if body.api_key_expires_on
        else None
    )
    garmin.store_token(account, token, token_expires_at)
    account.status = GarminStatus.ok
    account.last_error = None
    # La première synchro (tout l'historique) sera lancée ici quand les tâches de fond existeront.
    db.commit()
    return _out(account)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_garmin(user: CurrentUser, db: DbSession) -> None:
    """Oublie la clé et le jeton. Les données déjà synchronisées restent."""
    db.execute(delete(GarminAccount).where(GarminAccount.user_id == user.id))
    db.commit()
