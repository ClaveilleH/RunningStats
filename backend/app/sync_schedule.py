"""Quels membres synchroniser maintenant (appelé toutes les 5 min par le planificateur)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import jobs, settings
from app.config import get_settings
from app.models import GarminAccount, GarminStatus, Job, User
from app.settings import SyncSchedule


def in_night_pause(local: datetime, rules: SyncSchedule) -> bool:
    start, end, hour = rules.night_start_hour, rules.night_end_hour, local.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # pause à cheval sur minuit (ex. 22 h – 6 h)


def is_race_day(db: Session, user_id: int, local: datetime) -> bool:
    """Le membre est inscrit à une course aujourd'hui. Les courses n'existent pas encore."""
    return False


def due_user_ids(db: Session, now: datetime) -> list[int]:
    rules = settings.get(db, SyncSchedule)
    local = now.astimezone(ZoneInfo(get_settings().timezone))
    if in_night_pause(local, rules):
        return []

    # Dernière synchro lancée par membre : évite de relancer en boucle une synchro qui échoue.
    last_job = (
        select(Job.user_id, func.max(Job.created_at).label("at"))
        .where(Job.type == "garmin_sync")
        .group_by(Job.user_id)
        .subquery()
    )
    rows = db.execute(
        select(GarminAccount.user_id, GarminAccount.last_sync_at, User.sync_interval_minutes)
        .add_columns(last_job.c.at)
        .join(User, User.id == GarminAccount.user_id)
        .outerjoin(last_job, last_job.c.user_id == GarminAccount.user_id)
        # Clé expirée ou refusée : synchro suspendue jusqu'à une nouvelle clé.
        .where(
            GarminAccount.status == GarminStatus.ok, GarminAccount.api_key_encrypted.is_not(None)
        )
    ).all()

    due = []
    for user_id, last_sync_at, own_interval, last_job_at in rows:
        if is_race_day(db, user_id, local):
            interval = rules.race_day_interval_minutes
        else:
            interval = own_interval or rules.interval_minutes
        last = max((t for t in (last_sync_at, last_job_at) if t is not None), default=None)
        if last is None or now - last >= timedelta(minutes=interval):
            due.append(user_id)
    return due


def enqueue_due_syncs(db: Session, now: datetime) -> list[int]:
    user_ids = due_user_ids(db, now)
    for user_id in user_ids:
        jobs.enqueue_unless_queued(db, "garmin_sync", user_id=user_id)
    return user_ids
