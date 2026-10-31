"""Contrôle quotidien des clés Garmin (doc : chaque jour à 7 h)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import task
from app.models import GarminAccount, GarminStatus, Job
from app.security import utcnow

log = logging.getLogger(__name__)


@task("check_garmin_keys")
def check_garmin_keys(db: Session, job: Job) -> None:
    """Clé arrivée à expiration : statut « clé expirée », la synchro auto s'arrête.

    Le bandeau « expire bientôt » est déjà calculé à la lecture (GET /api/me/garmin).
    La ligne dans le journal admin viendra avec la table audit_log.
    """
    expired = db.scalars(
        select(GarminAccount).where(
            GarminAccount.api_key_expires_at <= utcnow(),
            GarminAccount.status != GarminStatus.key_expired,
        )
    ).all()
    for account in expired:
        account.status = GarminStatus.key_expired
        account.last_error = "La clé Garmin a expiré : enregistre une nouvelle clé dans Réglages."
    log.info("Clés Garmin : %s clé(s) passée(s) en expirée", len(expired))
