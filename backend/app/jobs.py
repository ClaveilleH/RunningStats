"""File de tâches de fond dans PostgreSQL (table jobs), sans Redis.

- Les routes et le planificateur mettent des tâches en file avec enqueue().
- Le worker (app/worker.py) les prend une par une avec run_one().
- Une tâche est une fonction enregistrée avec @task("nom"). Elle lève RetryableError pour
  un échec passager (Garmin 429 / 5xx, LLM) : elle est alors relancée selon retry_delays.
  Toute autre exception la met en échec tout de suite.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Job, JobStatus
from app.security import utcnow

log = logging.getLogger(__name__)

TaskHandler = Callable[[Session, Job], None]

# Délais de réessai définis par la doc : Garmin 1, 5 puis 30 min ; LLM 2 réessais.
GARMIN_RETRY_DELAYS = (60, 300, 1800)
LLM_RETRY_DELAYS = (60, 300)


class RetryableError(Exception):
    """Échec passager : la tâche sera relancée plus tard si elle a encore des essais."""


@dataclass(frozen=True)
class Task:
    handler: TaskHandler
    retry_delays: Sequence[int] = ()


TASKS: dict[str, Task] = {}


def task(name: str, *, retry_delays: Sequence[int] = ()) -> Callable[[TaskHandler], TaskHandler]:
    def register(handler: TaskHandler) -> TaskHandler:
        TASKS[name] = Task(handler, tuple(retry_delays))
        return handler

    return register


def enqueue(
    db: Session,
    type_: str,
    params: dict[str, Any] | None = None,
    *,
    user_id: int | None = None,
    delay: timedelta = timedelta(0),
) -> Job:
    job = Job(
        type=type_,
        params=params or {},
        user_id=user_id,
        status=JobStatus.pending,
        scheduled_at=utcnow() + delay,
    )
    db.add(job)
    db.flush()
    return job


def enqueue_unless_queued(
    db: Session, type_: str, params: dict[str, Any] | None = None, *, user_id: int | None = None
) -> Job:
    """Comme enqueue(), sauf si une tâche identique attend ou tourne déjà (ex. synchro)."""
    existing = db.scalar(
        select(Job).where(
            Job.type == type_,
            Job.user_id.is_(None) if user_id is None else Job.user_id == user_id,
            Job.status.in_([JobStatus.pending, JobStatus.running]),
        )
    )
    return existing or enqueue(db, type_, params, user_id=user_id)


def claim_next(db: Session) -> Job | None:
    """Prend la prochaine tâche due ; SKIP LOCKED évite que deux workers prennent la même."""
    now = utcnow()
    job = db.scalar(
        select(Job)
        .where(Job.status == JobStatus.pending, Job.scheduled_at <= now)
        .order_by(Job.scheduled_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is not None:
        job.status = JobStatus.running
        job.started_at = now
        job.finished_at = None
        job.attempts += 1
    return job


def _record_failure(job_id: int, error: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job is not None
        spec = TASKS.get(job.type)
        delays = spec.retry_delays if spec and isinstance(error, RetryableError) else ()
        job.error = f"{type(error).__name__}: {error}"[:2000]
        if job.attempts <= len(delays):
            job.status = JobStatus.pending
            job.scheduled_at = utcnow() + timedelta(seconds=delays[job.attempts - 1])
            log.warning("Tâche %s #%s : nouvel essai prévu (%s)", job.type, job.id, job.error)
        else:
            job.status = JobStatus.failed
            job.finished_at = utcnow()
            log.error("Tâche %s #%s en échec : %s", job.type, job.id, job.error)
        db.commit()


def run_one() -> bool:
    """Exécute une tâche due. Renvoie False s'il n'y avait rien à faire."""
    with SessionLocal() as db:
        job = claim_next(db)
        if job is None:
            return False
        job_id, job_type = job.id, job.type
        db.commit()

    log.info("Tâche %s #%s : début", job_type, job_id)
    try:
        spec = TASKS.get(job_type)
        if spec is None:
            raise LookupError(f"Type de tâche inconnu : {job_type}")
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            assert job is not None
            spec.handler(db, job)
            job.status = JobStatus.done
            job.error = None
            job.finished_at = utcnow()
            db.commit()
    except Exception as e:
        _record_failure(job_id, e)
    else:
        log.info("Tâche %s #%s : terminée", job_type, job_id)
    return True


def requeue_interrupted(db: Session) -> int:
    """Au démarrage du worker : remet en file les tâches coupées par un arrêt brutal."""
    result = db.execute(
        update(Job)
        .where(Job.status == JobStatus.running)
        .values(status=JobStatus.pending, scheduled_at=utcnow())
    )
    return result.rowcount


def retry(job: Job) -> None:
    """Relance manuelle d'une tâche en échec (bouton Relancer de l'admin)."""
    job.status = JobStatus.pending
    job.scheduled_at = utcnow()
    job.attempts = 0
    job.error = None
    job.started_at = None
    job.finished_at = None
