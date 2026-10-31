"""Synchro santé Garmin : sommeil, poids, pas, FC au repos, Body Battery, VFC."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import garmin, health
from app.config import get_settings
from app.jobs import GARMIN_RETRY_DELAYS, task
from app.models import Activity, GarminAccount, Job
from app.security import utcnow
from app.tasks.garmin_sync import _account, garmin_errors

log = logging.getLogger(__name__)

# Doc : après la première synchro, santé des 3 derniers jours (les valeurs de la veille
# et la nuit en cours peuvent encore bouger côté Garmin).
RECENT_DAYS = 3
# Premier passage sans activité connue : un an d'historique.
DEFAULT_HISTORY_DAYS = 365
# Taille des tranches de l'historique (une tranche = ~15 appels Garmin).
SLICE_DAYS = 366


def _window(db: Session, account: GarminAccount, today: date) -> tuple[date, date]:
    done_until = (account.sync_cursor or {}).get("health_until")
    if done_until:
        # Si le worker a été arrêté plusieurs jours, on rattrape depuis la dernière date.
        start = min(date.fromisoformat(done_until), today) - timedelta(days=RECENT_DAYS - 1)
        return start, today
    first: datetime | None = db.scalar(
        select(func.min(Activity.start_time)).where(Activity.user_id == account.user_id)
    )
    if first is None:
        return today - timedelta(days=DEFAULT_HISTORY_DAYS - 1), today
    return first.date(), today


def _fetch(
    db: Session,
    account: GarminAccount,
    start: date,
    end: date,
    max_days: int,
    method: Callable[[Any], Callable[[date, date], Any]],
) -> list[Any]:
    return [
        garmin.call(db, account, lambda c, a=a, b=b: method(c)(a, b))
        for a, b in health.chunks(start, end, max_days)
    ]


def _sync_slice(db: Session, account: GarminAccount, user_id: int, start: date, end: date) -> None:
    with garmin_errors(db):
        nights = _fetch(
            db, account, start, end, health.SLEEP_MAX_DAYS, lambda c: c.get_daily_sleep_summaries
        )
        days = _fetch(
            db, account, start, end, health.SUMMARIES_MAX_DAYS, lambda c: c.get_daily_summaries
        )
        weights = _fetch(
            db, account, start, end, health.WEIGHT_MAX_DAYS, lambda c: c.get_weight_measurements
        )
        hrv = _fetch(
            db, account, start, end, health.HRV_MAX_DAYS, lambda c: c.get_daily_hrv_summaries
        )
    health.store_sleep(db, [r for page in nights for r in health.sleep_rows(user_id, page)])
    health.store_daily(db, [r for page in days for r in health.daily_rows(user_id, page)])
    health.store_daily(db, [r for page in hrv for r in health.hrv_rows(user_id, page)])
    health.store_weights(db, [r for page in weights for r in health.weight_rows(user_id, page)])


@task("garmin_health", retry_delays=GARMIN_RETRY_DELAYS)
def garmin_health(db: Session, job: Job) -> None:
    """Données santé du membre : tout l'historique la première fois, puis les derniers jours.

    L'historique est lu par tranches d'un an, enregistrées une à une : si Garmin limite le
    débit (HTTP 429), la tâche réessaie plus tard et reprend après la dernière tranche.
    """
    user_id = job.user_id
    account = _account(db, user_id)
    if account is None or user_id is None:
        return
    today = utcnow().astimezone(ZoneInfo(get_settings().timezone)).date()
    start, end = _window(db, account, today)
    for slice_start, slice_end in health.chunks(start, end, SLICE_DAYS):
        _sync_slice(db, account, user_id, slice_start, slice_end)
        account.sync_cursor = {
            **(account.sync_cursor or {}),
            "health_until": slice_end.isoformat(),
        }
        db.commit()
    log.info("Santé du membre %s lue du %s au %s", user_id, start, end)
