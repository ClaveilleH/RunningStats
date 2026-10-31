from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les vraies tâches)
from app import jobs
from app.db import SessionLocal
from app.models import Invitation, Job, JobStatus, User, UserSession
from app.security import utcnow
from tests.conftest import login, make_user

calls: list[int] = []


def ok_handler(db: Session, job: Job) -> None:
    calls.append(job.id)


def flaky_handler(db: Session, job: Job) -> None:
    raise jobs.RetryableError("Garmin HTTP 503")


def broken_handler(db: Session, job: Job) -> None:
    raise ValueError("bug")


@pytest.fixture(autouse=True)
def test_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls.clear()
    monkeypatch.setitem(jobs.TASKS, "ok", jobs.Task(ok_handler))
    monkeypatch.setitem(jobs.TASKS, "flaky", jobs.Task(flaky_handler, (60, 300, 1800)))
    monkeypatch.setitem(jobs.TASKS, "broken", jobs.Task(broken_handler, (60,)))


def add_job(db: Session, type_: str, **kwargs: object) -> int:
    job = jobs.enqueue(db, type_, **kwargs)  # type: ignore[arg-type]
    db.commit()
    return job.id


def reload(db: Session, job_id: int) -> Job:
    db.expire_all()
    job = db.get(Job, job_id)
    assert job is not None
    return job


def make_due(db: Session, job_id: int) -> None:
    db.execute(update(Job).where(Job.id == job_id).values(scheduled_at=utcnow()))
    db.commit()


def test_success(db: Session) -> None:
    job_id = add_job(db, "ok")
    assert jobs.run_one() is True
    job = reload(db, job_id)
    assert job.status == JobStatus.done
    assert job.attempts == 1 and job.started_at and job.finished_at
    assert calls == [job_id]
    assert jobs.run_one() is False


def test_retryable_error_follows_delays_then_fails(db: Session) -> None:
    job_id = add_job(db, "flaky")
    for attempt, delay in enumerate((60, 300, 1800), start=1):
        before = utcnow()
        jobs.run_one()
        job = reload(db, job_id)
        assert job.status == JobStatus.pending, attempt
        assert job.attempts == attempt
        expected = before + timedelta(seconds=delay)
        assert abs((job.scheduled_at - expected).total_seconds()) < 5
        assert "503" in (job.error or "")
        # Pas relancée avant l'heure prévue.
        assert jobs.run_one() is False
        make_due(db, job_id)

    jobs.run_one()
    job = reload(db, job_id)
    assert job.status == JobStatus.failed
    assert job.attempts == 4
    assert job.finished_at is not None


def test_other_errors_fail_immediately(db: Session) -> None:
    job_id = add_job(db, "broken")
    jobs.run_one()
    job = reload(db, job_id)
    assert job.status == JobStatus.failed
    assert job.error == "ValueError: bug"


def test_unknown_type_fails(db: Session) -> None:
    job_id = add_job(db, "does-not-exist")
    jobs.run_one()
    assert reload(db, job_id).status == JobStatus.failed


def test_handler_changes_are_rolled_back_on_failure(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def writes_then_fails(db: Session, job: Job) -> None:
        job.params = {"half": "done"}
        db.flush()
        raise ValueError("bug")

    monkeypatch.setitem(jobs.TASKS, "half", jobs.Task(writes_then_fails))
    job_id = add_job(db, "half", params={"x": 1})
    jobs.run_one()
    assert reload(db, job_id).params == {"x": 1}


def test_delayed_job_waits(db: Session) -> None:
    add_job(db, "ok", delay=timedelta(minutes=10))
    assert jobs.run_one() is False


def test_skip_locked_two_workers_never_take_the_same_job(db: Session) -> None:
    first, second = add_job(db, "ok"), add_job(db, "ok")
    with SessionLocal() as worker_a, SessionLocal() as worker_b:
        job_a = jobs.claim_next(worker_a)  # verrou tenu, pas encore commité
        job_b = jobs.claim_next(worker_b)
        assert job_a is not None and job_b is not None
        assert {job_a.id, job_b.id} == {first, second}
        with SessionLocal() as worker_c:
            assert jobs.claim_next(worker_c) is None


def test_requeue_interrupted(db: Session) -> None:
    job_id = add_job(db, "ok")
    with SessionLocal() as worker:
        jobs.claim_next(worker)
        worker.commit()  # le worker "meurt" ici
    assert reload(db, job_id).status == JobStatus.running
    assert jobs.requeue_interrupted(db) == 1
    db.commit()
    assert reload(db, job_id).status == JobStatus.pending


def test_enqueue_unless_queued(db: Session, admin: User) -> None:
    first = jobs.enqueue_unless_queued(db, "ok", user_id=admin.id)
    again = jobs.enqueue_unless_queued(db, "ok", user_id=admin.id)
    system = jobs.enqueue_unless_queued(db, "ok")
    assert again.id == first.id
    assert system.id != first.id


def test_maintenance_purges_old_rows(db: Session, admin: User) -> None:
    now = utcnow()
    db.add_all(
        [
            UserSession(token_hash="a" * 64, user_id=admin.id, expires_at=now - timedelta(hours=1)),
            UserSession(token_hash="b" * 64, user_id=admin.id, expires_at=now + timedelta(days=1)),
            Invitation(token_hash="c" * 64, created_by_id=admin.id, expires_at=now),
            Invitation(
                token_hash="d" * 64, created_by_id=admin.id, expires_at=now + timedelta(days=1)
            ),
            Job(type="ok", status=JobStatus.done, finished_at=now - timedelta(days=31)),
            Job(type="ok", status=JobStatus.failed, finished_at=now - timedelta(days=31)),
            Job(type="ok", status=JobStatus.done, finished_at=now - timedelta(days=2)),
        ]
    )
    db.commit()
    maintenance_id = add_job(db, "maintenance")
    jobs.run_one()

    db.expire_all()
    assert reload(db, maintenance_id).status == JobStatus.done
    assert [s.token_hash[0] for s in db.scalars(select(UserSession))] == ["b"]
    assert [i.token_hash[0] for i in db.scalars(select(Invitation))] == ["d"]
    # Restent : la tâche récente et la maintenance elle-même.
    assert len(db.scalars(select(Job)).all()) == 2


def test_job_status_route_access(client: TestClient, db: Session, admin: User) -> None:
    bob = make_user(db, "bob@example.com")
    bob_job = add_job(db, "ok", user_id=bob.id)
    system_job = add_job(db, "ok")

    assert client.get(f"/api/jobs/{bob_job}").status_code == 401

    login(client, "bob@example.com")
    response = client.get(f"/api/jobs/{bob_job}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert client.get(f"/api/jobs/{system_job}").status_code == 404

    login(client, admin.email)
    assert client.get(f"/api/jobs/{system_job}").status_code == 200


def test_admin_list_and_retry(admin_client: TestClient, db: Session) -> None:
    job_id = add_job(db, "broken")
    jobs.run_one()

    listed = admin_client.get("/api/admin/jobs").json()
    assert [j["id"] for j in listed] == [job_id]
    assert listed[0]["status"] == "failed"

    response = admin_client.post(f"/api/admin/jobs/{job_id}/retry")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["attempts"] == 0
    assert admin_client.post(f"/api/admin/jobs/{job_id}/retry").status_code == 409


def test_members_cannot_see_admin_jobs(client: TestClient, db: Session) -> None:
    make_user(db, "bob@example.com")
    login(client, "bob@example.com")
    assert client.get("/api/admin/jobs").status_code == 403
