from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, GarminAccount, User
from tests.conftest import make_user
from tests.garmin_fakes import FakeGarminApi, build_fit, summary
from tests.test_activities import add
from tests.test_sync import sync


def synced(db: Session, admin: User, api: FakeGarminApi, **fit: int) -> Activity:
    """Une sortie passée par la vraie synchro (FIT lu, splits calculés)."""
    data = summary(1)
    data["elapsedDuration"] = 3100.0
    data["calories"] = 640
    data["averageRunningCadenceInStepsPerMinute"] = 168.0
    api.activities = [data]
    api.fits[1] = build_fit(**fit)
    sync(db, admin)
    activity = db.scalars(select(Activity)).one()
    return activity


def test_detail_has_summary_splits_zones_and_details(
    admin_client: TestClient, db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    activity = synced(db, admin, api, points=700, lap_every=200)  # 2,1 km à 3 m/s
    body = admin_client.get(f"/api/activities/{activity.id}").json()
    assert body["name"] == "Sortie 1"
    assert body["processed"] is True
    assert body["hr_zones_s"] == [60, 600, 1200, 900, 240]
    assert [s["index"] for s in body["km_splits"]] == [0, 1, 2]
    assert body["km_splits"][0]["end_distance_m"] == 1000
    assert len(body["laps"]) == 4  # tours de 200 s
    assert body["details"] == {
        "elapsed_s": 3100,
        "stopped_s": 100,
        "avg_cadence_spm": 168,
        "calories": 640,
        "min_altitude_m": None,
        "max_altitude_m": None,
    }


def test_points_are_thinned_with_smoothed_pace(
    admin_client: TestClient, db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    activity = synced(db, admin, api, points=700)
    body = admin_client.get(f"/api/activities/{activity.id}/points?step=30").json()
    assert body["step_m"] == 30
    lengths = {len(v) for k, v in body.items() if k != "step_m"}
    assert len(lengths) == 1
    assert body["distance_m"][:3] == [0, 30, 60]
    assert body["distance_m"][-1] == 699 * 3  # le dernier point est gardé
    # 3 m/s = 333 s/km.
    assert abs(body["pace_s_per_km"][10] - 1000 / 3) < 1
    assert body["lat"][0] == 45.0


def test_pace_ignores_pauses(
    admin_client: TestClient, db: Session, admin: User, api: FakeGarminApi, account: GarminAccount
) -> None:
    activity = synced(db, admin, api, points=400, pause_after=200, pause_s=120)
    body = admin_client.get(f"/api/activities/{activity.id}/points?step=30").json()
    i = body["distance_m"].index(600)  # point de la pause
    assert abs(body["pace_s_per_km"][i] - 1000 / 3) < 1


def test_pin_and_unpin(admin_client: TestClient, db: Session, admin: User) -> None:
    activity = add(db, admin, date(2026, 10, 1))
    assert admin_client.put(f"/api/activities/{activity.id}/pin").json()["pinned"] is True
    db.refresh(activity)
    assert activity.pinned is True
    assert admin_client.delete(f"/api/activities/{activity.id}/pin").json()["pinned"] is False


def test_unprocessed_activity_has_no_splits(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    activity = add(db, admin, date(2026, 10, 1))
    body = admin_client.get(f"/api/activities/{activity.id}").json()
    assert body["processed"] is False
    assert body["km_splits"] == []
    points = admin_client.get(f"/api/activities/{activity.id}/points").json()
    assert points["distance_m"] == []


def test_other_members_activity_is_not_found(admin_client: TestClient, db: Session) -> None:
    bob = make_user(db, "bob@example.com")
    activity = add(db, bob, date(2026, 10, 1))
    for path in ("", "/points"):
        assert admin_client.get(f"/api/activities/{activity.id}{path}").status_code == 404
    assert admin_client.put(f"/api/activities/{activity.id}/pin").status_code == 404
    assert admin_client.get("/api/activities/999").status_code == 404
