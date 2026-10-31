"""Synchro Garmin : liste des activités, puis traitement de chaque nouvelle activité."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import activities, fit, garmin
from app.jobs import GARMIN_RETRY_DELAYS, RetryableError, enqueue, task
from app.models import Activity, GarminAccount, GarminStatus, Job
from app.security import utcnow

log = logging.getLogger(__name__)

PAGE_SIZE = 100


@contextmanager
def garmin_errors(db: Session) -> Iterator[None]:
    """Traduit les erreurs Garmin pour la file de tâches."""
    try:
        yield
    except garmin.GarminUnavailable as e:
        raise RetryableError(str(e)) from e
    except garmin.GarminKeyRejected:
        # Garder le statut « erreur » / « clé expirée » malgré l'échec de la tâche.
        db.commit()
        raise


def _account(db: Session, user_id: int | None) -> GarminAccount | None:
    if user_id is None:
        return None
    account = db.scalar(select(GarminAccount).where(GarminAccount.user_id == user_id))
    return account if account and account.api_key_encrypted else None


@task("garmin_sync", retry_delays=GARMIN_RETRY_DELAYS)
def garmin_sync(db: Session, job: Job) -> None:
    """Nouvelles activités course et trail du membre.

    Garmin renvoie les activités des plus récentes aux plus anciennes. Tant que l'historique
    n'a pas été parcouru en entier, on lit toutes les pages ; ensuite on s'arrête à la
    première activité déjà connue.
    """
    user_id = job.user_id
    account = _account(db, user_id)
    if account is None or user_id is None:
        log.info("Synchro ignorée : pas de clé Garmin pour le membre %s", user_id)
        return

    history_complete = bool((account.sync_cursor or {}).get("history_complete"))
    known = set(db.scalars(select(Activity.garmin_id).where(Activity.user_id == user_id)))
    added = 0
    start = 0
    reached_known = False

    with garmin_errors(db):
        while True:
            page = (
                garmin.call(
                    db,
                    account,
                    lambda c, start=start: c.search_activities(start=start, limit=PAGE_SIZE),
                )
                or []
            )
            for summary in page:
                garmin_id = int(summary["activityId"])
                if garmin_id in known:
                    if history_complete:
                        reached_known = True
                        break
                    continue
                if not activities.is_running(summary):
                    continue
                activity = activities.activity_from_summary(user_id, summary)
                db.add(activity)
                db.flush()
                enqueue(db, "process_activity", {"activity_id": activity.id}, user_id=user_id)
                known.add(garmin_id)
                added += 1
            # Chaque page est gardée : une synchro coupée reprend sans tout refaire.
            db.commit()
            if reached_known or len(page) < PAGE_SIZE:
                break
            start += PAGE_SIZE

    account.sync_cursor = {**(account.sync_cursor or {}), "history_complete": True}
    account.last_sync_at = utcnow()
    account.status = GarminStatus.ok
    account.last_error = None
    log.info("Synchro du membre %s : %s nouvelle(s) activité(s)", user_id, added)


@task("process_activity", retry_delays=GARMIN_RETRY_DELAYS)
def process_activity(db: Session, job: Job) -> None:
    """Télécharge le FIT, le garde brut et en extrait les points et les tours."""
    activity = db.get(Activity, job.params["activity_id"])
    if activity is None:
        return
    account = _account(db, activity.user_id)
    if account is None:
        log.info("Activité %s non traitée : plus de clé Garmin", activity.id)
        return

    with garmin_errors(db):
        content = garmin.call(db, account, lambda c: c.download_activity(activity.garmin_id))
    activities.save_raw_fit(activity, content)
    parsed = fit.parse(content)
    activities.store_fit_data(db, activity, parsed)
    log.info("Activité %s : %s points, %s tours", activity.id, len(parsed.points), len(parsed.laps))
