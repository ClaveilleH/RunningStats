from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import activities, health, jobs
from app.models import DailyHealth, GarminAccount, Job, JobStatus, SleepNight, User, Weight
from app.tasks import garmin_health as health_module
from tests.garmin_fakes import FakeGarminApi, daily_summary, night, summary, weighing
from tests.test_sync import run_all, sync

# 31/10/2026 à 12 h UTC : 31/10 à Paris.
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 31)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "utcnow", lambda: NOW)


def health_sync(db: Session, user: User) -> Job:
    job = jobs.enqueue(db, "garmin_health", user_id=user.id)
    db.commit()
    run_all()
    db.refresh(job)
    return job


def test_chunks_respect_garmin_limits() -> None:
    periods = health.chunks(date(2026, 1, 1), date(2026, 3, 1), 31)
    assert periods == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 3, 1)),
    ]
    assert health.chunks(date(2026, 1, 2), date(2026, 1, 1), 31) == []


def test_activity_sync_enqueues_health(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    api.activities = [summary(1)]
    api.nights = {"2026-10-30": night("2026-10-30")}
    sync(db, admin)
    done = db.scalars(select(Job).where(Job.type == "garmin_health")).all()
    assert [j.status for j in done] == [JobStatus.done]
    assert db.scalar(select(SleepNight)) is not None


def test_first_sync_reads_history_from_first_activity(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    api.activities = [summary(1, days_ago=100)]  # sortie du 17/07/2026
    sync(db, admin)
    sleep_calls = [(a, b) for name, a, b in api.health_calls if name == "sleep"]
    assert sleep_calls[0][0] == date(2026, 7, 17)
    assert sleep_calls[-1][1] == TODAY
    assert all((b - a).days < health.SLEEP_MAX_DAYS for a, b in sleep_calls)
    assert len(sleep_calls) == 4  # 107 jours en périodes de 31 jours
    summary_calls = [c for c in api.health_calls if c[0] == "summaries"]
    assert len(summary_calls) == 1
    db.refresh(account)
    assert account.sync_cursor["health_until"] == "2026-10-31"


def test_next_syncs_read_last_three_days(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    account.sync_cursor = {"history_complete": True, "health_until": "2026-10-31"}
    db.commit()
    health_sync(db, admin)
    assert {(a, b) for _, a, b in api.health_calls} == {(date(2026, 10, 29), TODAY)}


def test_catch_up_after_a_long_stop(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    account.sync_cursor = {"health_until": "2026-10-20"}
    db.commit()
    health_sync(db, admin)
    assert {a for _, a, _ in api.health_calls} == {date(2026, 10, 18)}


def test_without_activity_one_year_of_history(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    health_sync(db, admin)
    first = min(a for _, a, _ in api.health_calls)
    assert first == TODAY - timedelta(days=364)


def test_values_are_stored(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    account.sync_cursor = {"health_until": "2026-10-31"}
    db.commit()
    api.nights = {
        "2026-10-30": night("2026-10-30", total_s=25000, score=72),
        "2026-10-31": night("2026-10-31", total_s=0),  # pas de nuit enregistrée
    }
    api.days = {"2026-10-30": daily_summary("2026-10-30", steps=12000, resting_hr=48)}
    api.hrv = {"2026-10-30": {"calendarDate": "2026-10-30", "lastNightAvg": 62}}
    api.weighings = [weighing(11, "2026-10-30", 70500), weighing(12, "2026-10-30", 70100)]
    health_sync(db, admin)

    sleep = db.scalars(select(SleepNight)).all()
    assert [(s.date, s.total_s, s.score, s.deep_s) for s in sleep] == [
        (date(2026, 10, 30), 25000, 72, 5400)
    ]
    assert sleep[0].start_time == datetime(2026, 10, 23, 22, 33, tzinfo=UTC)
    assert sleep[0].raw["sleepScores"]["overall"]["value"] == 72
    day = db.scalars(select(DailyHealth)).one()
    assert (day.steps, day.resting_hr, day.body_battery_min, day.body_battery_max) == (
        12000,
        48,
        15,
        80,
    )
    assert day.hrv_ms == 62
    assert sorted(w.weight_kg for w in db.scalars(select(Weight))) == [70.1, 70.5]


def test_resync_updates_without_duplicates(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    account.sync_cursor = {"health_until": "2026-10-31"}
    db.commit()
    api.days = {"2026-10-30": daily_summary("2026-10-30", steps=3000)}
    api.hrv = {"2026-10-30": {"calendarDate": "2026-10-30", "lastNightAvg": 60}}
    api.weighings = [weighing(11, "2026-10-30")]
    health_sync(db, admin)
    api.days = {"2026-10-30": daily_summary("2026-10-30", steps=9500)}
    api.hrv = {}  # la VFC absente ne doit pas effacer celle déjà connue
    health_sync(db, admin)

    day = db.scalars(select(DailyHealth)).one()
    assert (day.steps, day.hrv_ms) == (9500, 60)
    assert len(db.scalars(select(Weight)).all()) == 1


def test_garmin_unavailable_is_retried(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    api.errors = [503]
    job = health_sync(db, admin)
    assert job.status == JobStatus.pending
    assert job.attempts == 1


def test_rate_limit_keeps_finished_slices(
    db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    db.add(activities.activity_from_summary(admin.id, summary(1, days_ago=800)))  # 16/08/2024
    db.commit()
    api.nights = {"2025-01-10": night("2025-01-10")}
    api.health_limit = 17  # la 1re tranche (un an) prend 15 appels
    job = health_sync(db, admin)

    assert job.status == JobStatus.pending  # nouvel essai prévu
    db.refresh(account)
    assert account.sync_cursor["health_until"] == "2025-08-16"
    assert db.scalar(select(SleepNight.date)) == date(2025, 1, 10)

    api.health_limit = None
    api.health_calls.clear()
    job.scheduled_at = datetime.now(UTC)  # sans attendre le délai du nouvel essai
    db.commit()
    run_all()
    # Reprise juste avant la fin de la tranche gardée (3 derniers jours relus).
    assert min(a for _, a, _ in api.health_calls) == date(2025, 8, 14)
    db.refresh(account)
    assert account.sync_cursor["health_until"] == "2026-10-31"
