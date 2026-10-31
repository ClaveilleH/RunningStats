from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import activities, crypto, fit, garmin, jobs
from app.config import get_settings
from app.models import (
    Activity,
    ActivityLap,
    ActivityPoint,
    GarminAccount,
    GarminStatus,
    Job,
    JobStatus,
    User,
)
from app.security import utcnow
from app.tasks import garmin_sync as sync_module
from tests.garmin_fakes import FakeGarminApi, build_fit, summary


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeGarminApi:
    fake = FakeGarminApi()
    monkeypatch.setattr(garmin, "GarminPersonalApiClient", fake.client)
    monkeypatch.setattr(garmin, "_throttle", lambda: None)
    monkeypatch.setattr(garmin, "_request_token", lambda key: _jwt())
    return fake


def _jwt() -> str:
    from tests.test_garmin import fake_jwt

    return fake_jwt(utcnow() + timedelta(hours=24))


@pytest.fixture
def account(db: Session, admin: User) -> GarminAccount:
    account = GarminAccount(user_id=admin.id, api_key_encrypted=crypto.encrypt("key"))
    garmin.store_token(account, "token", utcnow() + timedelta(hours=10))
    db.add(account)
    db.commit()
    return account


def sync(db: Session, user: User) -> int:
    """Lance une synchro et vide la file (traitements d'activités compris)."""
    job = jobs.enqueue(db, "garmin_sync", user_id=user.id)
    db.commit()
    run_all()
    return job.id


def run_all() -> None:
    while jobs.run_one():
        pass


def job_status(db: Session, job_id: int) -> JobStatus:
    db.expire_all()
    job = db.get(Job, job_id)
    assert job is not None
    return job.status


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --- Lecture du FIT et du résumé -------------------------------------------------------------


def test_parse_fit() -> None:
    parsed = fit.parse(build_fit(points=11, lap_every=5))
    assert len(parsed.points) == 11
    first, last = parsed.points[0], parsed.points[-1]
    assert first["t_s"] == 0 and last["t_s"] == 10
    assert first["lat"] == pytest.approx(45.0, abs=1e-6)
    assert first["lon"] == pytest.approx(6.0, abs=1e-6)
    assert last["altitude_m"] == pytest.approx(110.0)
    assert last["distance_m"] == pytest.approx(30.0)
    assert first["hr"] == 140
    # Cadence FIT 80 (une jambe) = 160 pas / min.
    assert first["cadence_spm"] == 160
    assert [(lap["start_distance_m"], lap["end_distance_m"]) for lap in parsed.laps] == [
        (0.0, 15.0),
        (15.0, 30.0),
    ]


def test_parse_fit_excludes_pauses_from_timer() -> None:
    parsed = fit.parse(build_fit(points=11, pause_after=4, pause_s=60))
    times = [(p["t_s"], p["timer_s"]) for p in parsed.points]
    assert times[4] == (4.0, 4.0)  # point au moment de l'arrêt du chrono
    assert times[5] == (65.0, 5.0)  # premier point après la reprise
    assert times[-1] == (70.0, 10.0)


def test_parse_accepts_bare_fit_and_rejects_garbage() -> None:
    assert len(fit.parse(build_fit(points=3, zipped=False)).points) == 3
    with pytest.raises(ValueError):
        fit.parse(b"not a fit file")


def test_activity_from_summary() -> None:
    activity = activities.activity_from_summary(1, summary(42, "trail_running"))
    assert activity.garmin_id == 42
    assert activity.activity_type == "trail_running"
    assert activity.start_time == datetime(2026, 10, 25, 8, 0, tzinfo=UTC)
    assert activity.start_time_local == datetime(2026, 10, 25, 9, 0)
    assert activity.avg_hr == 150
    assert activity.hr_zones_s == [60.0, 600.0, 1200.0, 900.0, 240.0]


# --- Synchro -----------------------------------------------------------------------------------


def test_first_sync_keeps_only_running_types_across_pages(
    db: Session,
    admin: User,
    account: GarminAccount,
    api: FakeGarminApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PAGE_SIZE", 2)
    api.activities = [
        summary(5, "running", 0),
        summary(4, "hiking", 1),
        summary(3, "trail_running", 2),
        summary(2, "treadmill_running", 3),
        summary(1, "track_running", 4),
    ]
    job_id = sync(db, admin)

    assert job_status(db, job_id) == JobStatus.done
    assert api.search_calls == [0, 2, 4]
    assert sorted(db.scalars(select(Activity.garmin_id))) == [1, 3, 5]
    db.refresh(account)
    assert account.sync_cursor == {"history_complete": True}
    assert account.last_sync_at is not None
    # Une tâche de traitement par activité gardée.
    pending = db.scalars(select(Job).where(Job.type == "process_activity")).all()
    assert len(pending) == 3


def test_process_activity_stores_points_laps_and_raw_fit(
    db: Session, admin: User, account: GarminAccount, api: FakeGarminApi
) -> None:
    api.activities = [summary(7)]
    api.fits[7] = build_fit(points=11, lap_every=5)
    sync(db, admin)
    run_all()

    activity = db.scalar(select(Activity))
    assert activity is not None
    assert activity.processed_at is not None
    # Les métriques sont calculées dans la foulée.
    assert activity.category is not None and activity.km_effort is not None
    assert activity.fit_path == f"fit/{admin.id}/7.zip"
    assert (get_settings().data_dir / activity.fit_path).read_bytes() == api.fits[7]
    assert count(db, ActivityPoint) == 11
    # 2 tours de la montre + 1 split (30 m, moins d'un km).
    assert count(db, ActivityLap) == 3

    # Retraiter remplace les données au lieu de les dupliquer.
    jobs.enqueue(db, "process_activity", {"activity_id": activity.id}, user_id=admin.id)
    db.commit()
    run_all()
    assert count(db, ActivityPoint) == 11
    assert count(db, ActivityLap) == 3


def test_next_sync_stops_at_first_known_activity(
    db: Session,
    admin: User,
    account: GarminAccount,
    api: FakeGarminApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PAGE_SIZE", 2)
    api.activities = [summary(i, days_ago=10 - i) for i in (3, 2, 1)]
    sync(db, admin)

    api.activities.insert(0, summary(4))
    api.search_calls.clear()
    sync(db, admin)

    assert api.search_calls == [0]
    assert sorted(db.scalars(select(Activity.garmin_id))) == [1, 2, 3, 4]


def test_interrupted_first_sync_resumes_past_known_activities(
    db: Session,
    admin: User,
    account: GarminAccount,
    api: FakeGarminApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PAGE_SIZE", 2)
    api.activities = [summary(i, days_ago=10 - i) for i in (4, 3, 2, 1)]
    # Garmin tombe sur la 2e page : la 1re page est gardée, la tâche sera réessayée.
    original = api.client

    calls = {"n": 0}

    def flaky_client(token: str, **kw: object):  # type: ignore[no-untyped-def]
        client = original(token)
        calls["n"] += 1
        if calls["n"] == 2:
            api.errors.append(503)
        return client

    monkeypatch.setattr(garmin, "GarminPersonalApiClient", flaky_client)
    job_id = sync(db, admin)
    assert job_status(db, job_id) == JobStatus.pending  # réessai prévu
    assert sorted(db.scalars(select(Activity.garmin_id))) == [3, 4]

    # Le réessai repart du début et va au bout malgré les activités déjà connues.
    db.execute(Job.__table__.update().where(Job.id == job_id).values(scheduled_at=utcnow()))
    db.commit()
    jobs.run_one()
    assert job_status(db, job_id) == JobStatus.done
    assert sorted(db.scalars(select(Activity.garmin_id))) == [1, 2, 3, 4]


def test_garmin_unavailable_schedules_a_retry(
    db: Session, admin: User, account: GarminAccount, api: FakeGarminApi
) -> None:
    api.errors = [429]
    job_id = sync(db, admin)
    db.expire_all()
    job = db.get(Job, job_id)
    assert job is not None
    assert job.status == JobStatus.pending
    assert job.attempts == 1
    assert "429" in (job.error or "")


def test_refused_access_marks_account_in_error(
    db: Session, admin: User, account: GarminAccount, api: FakeGarminApi
) -> None:
    api.errors = [401, 401]
    job_id = sync(db, admin)
    assert job_status(db, job_id) == JobStatus.failed
    db.refresh(account)
    assert account.status == GarminStatus.error
    assert account.last_error


def test_single_401_renews_token_and_continues(
    db: Session, admin: User, account: GarminAccount, api: FakeGarminApi
) -> None:
    api.activities = [summary(1)]
    api.errors = [401]
    job_id = sync(db, admin)
    assert job_status(db, job_id) == JobStatus.done
    db.refresh(account)
    assert account.status == GarminStatus.ok
    assert crypto.decrypt(account.token_encrypted or "") != "token"


def test_sync_without_account_does_nothing(db: Session, admin: User, api: FakeGarminApi) -> None:
    job_id = sync(db, admin)
    assert job_status(db, job_id) == JobStatus.done
    assert api.search_calls == []


# --- Routes ------------------------------------------------------------------------------------


def test_manual_sync_route(
    admin_client: TestClient, db: Session, admin: User, api: FakeGarminApi
) -> None:
    assert admin_client.post("/api/me/sync").status_code == 409

    db.add(GarminAccount(user_id=admin.id, api_key_encrypted=crypto.encrypt("key")))
    db.commit()
    first = admin_client.post("/api/me/sync")
    assert first.status_code == 202
    # Une synchro déjà en file est réutilisée.
    assert admin_client.post("/api/me/sync").json() == first.json()


def test_saving_a_key_starts_the_first_sync(
    admin_client: TestClient, db: Session, api: FakeGarminApi
) -> None:
    response = admin_client.put("/api/me/garmin", json={"api_key": "key"})
    job = db.get(Job, response.json()["sync_job_id"])
    assert job is not None and job.type == "garmin_sync"


def test_reprocess_from_local_fit_without_garmin(
    db: Session, admin: User, account: GarminAccount, api: FakeGarminApi
) -> None:
    api.activities = [summary(7)]
    sync(db, admin)
    activity = db.scalar(select(Activity))
    assert activity is not None
    downloads = len(api.downloads)

    db.delete(account)
    db.commit()
    jobs.enqueue(
        db,
        "process_activity",
        {"activity_id": activity.id, "use_local_fit": True},
        user_id=admin.id,
    )
    db.commit()
    run_all()
    assert len(api.downloads) == downloads
    db.refresh(activity)
    assert activity.calc_trace is not None
