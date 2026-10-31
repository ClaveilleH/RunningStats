"""Maintenance de nuit : purge des sessions, invitations et tâches périmées."""

import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.jobs import task
from app.models import Invitation, Job, JobStatus, UserSession
from app.security import utcnow

log = logging.getLogger(__name__)

FINISHED_JOBS_KEPT = timedelta(days=30)


@task("maintenance")
def maintenance(db: Session, job: Job) -> None:
    now = utcnow()
    sessions = db.execute(delete(UserSession).where(UserSession.expires_at <= now)).rowcount
    invitations = db.execute(
        delete(Invitation).where(Invitation.expires_at <= now, Invitation.used_at.is_(None))
    ).rowcount
    jobs = db.execute(
        delete(Job).where(
            Job.status.in_([JobStatus.done, JobStatus.failed]),
            Job.finished_at <= now - FINISHED_JOBS_KEPT,
        )
    ).rowcount
    log.info(
        "Maintenance : %s sessions, %s invitations, %s tâches supprimées",
        sessions,
        invitations,
        jobs,
    )
