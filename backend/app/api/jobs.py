from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.models import Job, Role
from app.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: CurrentUser, db: DbSession) -> Job:
    """Suivi d'une tâche lancée par une route en 202. Un membre ne voit que les siennes."""
    job = db.get(Job, job_id)
    if job is None or (user.role != Role.admin and job.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return job
