"""Recalcul des métriques de toutes les activités (après un changement de seuils)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import metrics, settings
from app.jobs import task
from app.models import Activity, Job
from app.settings import ActivityCategories

log = logging.getLogger(__name__)

BATCH = 50


@task("recompute_metrics")
def recompute_metrics(db: Session, job: Job) -> None:
    rules = settings.get(db, ActivityCategories)
    ids = list(db.scalars(select(Activity.id).order_by(Activity.id)))
    for start in range(0, len(ids), BATCH):
        for activity_id in ids[start : start + BATCH]:
            activity = db.get(Activity, activity_id)
            if activity is not None:
                metrics.compute(db, activity, rules)
        db.commit()
    log.info("Métriques recalculées pour %s activités", len(ids))
