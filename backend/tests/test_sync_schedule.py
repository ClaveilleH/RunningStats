from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import crypto, jobs, sync_schedule
from app.models import GarminAccount, GarminStatus, Job, JobStatus, User
from app.settings import SyncSchedule
from tests.conftest import make_user

# 31/10/2026 14 h UTC = 15 h à Paris (heure d'hiver).
AFTERNOON = datetime(2026, 10, 31, 14, 0, tzinfo=UTC)
# 1er/11/2026 2 h UTC = 3 h à Paris : pause de nuit.
NIGHT = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)


def connect(db: Session, user: User, **fields: object) -> GarminAccount:
    account = GarminAccount(user_id=user.id, api_key_encrypted=crypto.encrypt("key"), **fields)
    db.add(account)
    db.commit()
    return account


def test_night_pause() -> None:
    rules = SyncSchedule()
    assert sync_schedule.in_night_pause(datetime(2026, 1, 1, 3), rules)
    assert not sync_schedule.in_night_pause(datetime(2026, 1, 1, 6), rules)
    wrap = SyncSchedule(night_start_hour=22, night_end_hour=6)
    assert sync_schedule.in_night_pause(datetime(2026, 1, 1, 23), wrap)
    assert sync_schedule.in_night_pause(datetime(2026, 1, 1, 5), wrap)
    assert not sync_schedule.in_night_pause(datetime(2026, 1, 1, 12), wrap)
    assert not sync_schedule.in_night_pause(datetime(2026, 1, 1, 3), SyncSchedule(night_end_hour=0))


def test_never_synced_member_is_due(db: Session, admin: User) -> None:
    connect(db, admin)
    assert sync_schedule.due_user_ids(db, AFTERNOON) == [admin.id]


def test_nothing_during_the_night(db: Session, admin: User) -> None:
    connect(db, admin)
    assert sync_schedule.due_user_ids(db, NIGHT) == []


def test_group_interval(db: Session, admin: User) -> None:
    connect(db, admin, last_sync_at=AFTERNOON - timedelta(minutes=59))
    assert sync_schedule.due_user_ids(db, AFTERNOON) == []
    assert sync_schedule.due_user_ids(db, AFTERNOON + timedelta(minutes=1)) == [admin.id]


def test_member_interval_overrides_group(db: Session, admin: User) -> None:
    admin.sync_interval_minutes = 15
    connect(db, admin, last_sync_at=AFTERNOON - timedelta(minutes=20))
    assert sync_schedule.due_user_ids(db, AFTERNOON) == [admin.id]


def test_failing_sync_is_not_relaunched_every_tick(db: Session, admin: User) -> None:
    connect(db, admin, last_sync_at=AFTERNOON - timedelta(hours=5))
    failed = Job(
        type="garmin_sync",
        user_id=admin.id,
        status=JobStatus.failed,
        created_at=AFTERNOON - timedelta(minutes=30),
    )
    db.add(failed)
    db.commit()
    assert sync_schedule.due_user_ids(db, AFTERNOON) == []
    assert sync_schedule.due_user_ids(db, AFTERNOON + timedelta(minutes=31)) == [admin.id]


@pytest.mark.parametrize("status", [GarminStatus.error, GarminStatus.key_expired])
def test_suspended_accounts_are_skipped(db: Session, admin: User, status: GarminStatus) -> None:
    connect(db, admin, status=status)
    assert sync_schedule.due_user_ids(db, AFTERNOON) == []


def test_members_without_garmin_are_skipped(db: Session, admin: User) -> None:
    make_user(db, "bob@example.com")
    connect(db, admin)
    assert sync_schedule.due_user_ids(db, AFTERNOON) == [admin.id]


def test_enqueue_due_syncs_does_not_duplicate(db: Session, admin: User) -> None:
    connect(db, admin)
    sync_schedule.enqueue_due_syncs(db, AFTERNOON)
    sync_schedule.enqueue_due_syncs(db, AFTERNOON + timedelta(hours=2))
    db.commit()
    assert len(db.scalars(select(Job).where(Job.type == "garmin_sync")).all()) == 1


def test_schedule_is_an_admin_setting(admin_client: TestClient, db: Session, admin: User) -> None:
    response = admin_client.put(
        "/api/admin/settings", json={"sync_schedule": {"interval_minutes": 30}}
    )
    assert response.status_code == 200
    connect(db, admin, last_sync_at=AFTERNOON - timedelta(minutes=31))
    assert sync_schedule.due_user_ids(db, AFTERNOON) == [admin.id]
    too_often = {"sync_schedule": {"interval_minutes": 1}}
    assert admin_client.put("/api/admin/settings", json=too_often).status_code == 422


def test_check_garmin_keys_marks_expired_keys(db: Session, admin: User) -> None:
    account = connect(db, admin, api_key_expires_at=datetime(2026, 1, 1, tzinfo=UTC))
    bob = make_user(db, "bob@example.com")
    valid = connect(db, bob, api_key_expires_at=datetime(2099, 1, 1, tzinfo=UTC))
    jobs.enqueue(db, "check_garmin_keys")
    db.commit()
    jobs.run_one()
    db.refresh(account)
    db.refresh(valid)
    assert account.status == GarminStatus.key_expired
    assert valid.status == GarminStatus.ok
