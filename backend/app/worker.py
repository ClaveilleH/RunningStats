"""Worker des tâches de fond : uv run python -m app.worker

Un seul processus, à côté de l'API :
- APScheduler planifie les tâches récurrentes ; il ne fait que les mettre en file ;
- la boucle principale exécute les tâches de la file une par une.
"""

import logging
import signal
import time
from types import FrameType

from apscheduler.schedulers.background import BackgroundScheduler

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import jobs, sync_schedule
from app.config import get_settings
from app.db import SessionLocal
from app.security import utcnow

log = logging.getLogger("app.worker")


def _enqueue_unless_queued(type_: str) -> None:
    with SessionLocal() as db:
        jobs.enqueue_unless_queued(db, type_)
        db.commit()


def _enqueue_due_syncs() -> None:
    with SessionLocal() as db:
        user_ids = sync_schedule.enqueue_due_syncs(db, utcnow())
        db.commit()
    if user_ids:
        log.info("Synchro automatique lancée pour : %s", user_ids)


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=get_settings().timezone)
    # Doc : maintenance chaque nuit à 3 h.
    scheduler.add_job(
        _enqueue_unless_queued, "cron", hour=3, minute=0, args=["maintenance"], id="maintenance"
    )
    # Doc : contrôle des clés Garmin chaque jour à 7 h.
    scheduler.add_job(
        _enqueue_unless_queued,
        "cron",
        hour=7,
        minute=0,
        args=["check_garmin_keys"],
        id="check_garmin_keys",
    )
    # Synchro automatique : toutes les 5 min on regarde quels membres sont dus
    # (fréquence et pause de nuit dans app_settings, 10 min les jours de course).
    scheduler.add_job(
        _enqueue_due_syncs, "interval", minutes=5, id="garmin_sync", next_run_time=utcnow()
    )
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    with SessionLocal() as db:
        requeued = jobs.requeue_interrupted(db)
        db.commit()
    if requeued:
        log.warning("%s tâche(s) interrompue(s) remise(s) en file", requeued)

    stopping = False

    def stop(signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        log.info("Arrêt demandé (signal %s), fin de la tâche en cours…", signum)
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    scheduler = build_scheduler()
    scheduler.start()
    log.info("Worker démarré (%s tâches connues : %s)", len(jobs.TASKS), ", ".join(jobs.TASKS))
    try:
        while not stopping:
            if not jobs.run_one():
                time.sleep(settings.worker_poll_seconds)
    finally:
        scheduler.shutdown(wait=False)
        log.info("Worker arrêté")


if __name__ == "__main__":
    main()
