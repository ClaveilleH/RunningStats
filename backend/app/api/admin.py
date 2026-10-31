from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select

from app import accounts, jobs, settings
from app.api.deps import AdminUser, DbSession
from app.models import Job, JobStatus
from app.schemas import InvitationOut, JobOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def create_invitation(admin: AdminUser, db: DbSession) -> InvitationOut:
    invitation, token = accounts.create_invitation(db, created_by=admin)
    db.commit()
    # Le front construit le lien d'invitation à partir du jeton.
    return InvitationOut(token=token, expires_at=invitation.expires_at)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    _: AdminUser, db: DbSession, limit: int = Query(default=50, ge=1, le=200)
) -> list[Job]:
    """Tâches récentes et en cours, les plus récentes d'abord."""
    return list(db.scalars(select(Job).order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)))


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, _: AdminUser, db: DbSession) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    if job.status != JobStatus.failed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Seule une tâche en échec peut être relancée."
        )
    jobs.retry(job)
    db.commit()
    return job


# Réglages dont le changement oblige à recalculer les activités déjà en base.
RECOMPUTE_ON_CHANGE = {"activity_categories": "recompute_metrics"}


@router.get("/settings")
def get_settings(_: AdminUser, db: DbSession) -> dict[str, dict[str, Any]]:
    """Tous les réglages du groupe, valeurs par défaut comprises."""
    return settings.all_settings(db)


@router.put("/settings")
def put_settings(
    body: dict[str, dict[str, Any]], _: AdminUser, db: DbSession
) -> dict[str, dict[str, Any]]:
    """Met à jour un ou plusieurs réglages. Les champs absents gardent leur valeur actuelle."""
    current = settings.all_settings(db)
    for key, changes in body.items():
        if key not in settings.REGISTRY:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Réglage inconnu : {key}")
        try:
            settings.save(db, key, {**current[key], **changes})
        except ValidationError as e:
            message = e.errors()[0]["msg"].removeprefix("Value error, ")
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from e
        if key in RECOMPUTE_ON_CHANGE and settings.all_settings(db)[key] != current[key]:
            jobs.enqueue_unless_queued(db, RECOMPUTE_ON_CHANGE[key])
    db.commit()
    return settings.all_settings(db)
