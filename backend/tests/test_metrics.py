import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import activities, jobs, metrics
from app.models import Activity, ActivityLap, ActivityPoint, Job, LapKind, User
from app.settings import ActivityCategories
from tests.conftest import login, make_user
from tests.garmin_fakes import summary

RULES = ActivityCategories()


def point(
    seq: int,
    t: float,
    d: float,
    alt: float | None = 100.0,
    hr: int = 150,
    timer: float | None = None,
) -> ActivityPoint:
    return ActivityPoint(seq=seq, t_s=t, timer_s=timer, distance_m=d, altitude_m=alt, hr=hr)


# --- Catégorie et km-effort --------------------------------------------------------------------


def test_km_effort() -> None:
    assert metrics.km_effort(21100, 1200) == pytest.approx(33.1)


@pytest.mark.parametrize(
    ("activity_type", "distance_m", "gain_m", "expected"),
    [
        ("running", 10000, 50, "road"),  # 5 m/km
        ("running", 10000, 150, "mixed"),  # 15 m/km
        ("running", 10000, 400, "short_trail"),  # 40 m/km, 14 km-effort
        ("running", 30000, 1500, "long_trail"),  # 50 m/km, 45 km-effort
        ("trail_running", 10000, 50, "mixed"),  # marqué trail mais plat
        ("trail_running", 10000, 150, "short_trail"),  # marqué trail, vallonné
        ("track_running", 5000, 0, "road"),
        ("running", 0, 0, "road"),
    ],
)
def test_classify(activity_type: str, distance_m: float, gain_m: float, expected: str) -> None:
    category, trace = metrics.classify(activity_type, distance_m, gain_m, RULES)
    assert category == expected
    assert trace["params"]["trail_min_dplus_per_km"] == 25


def test_classify_thresholds_are_settings() -> None:
    rules = ActivityCategories(road_max_dplus_per_km=20, trail_min_dplus_per_km=30)
    assert metrics.classify("running", 10000, 150, rules)[0] == "road"


def test_settings_reject_inverted_thresholds() -> None:
    with pytest.raises(ValueError):
        ActivityCategories(road_max_dplus_per_km=30, trail_min_dplus_per_km=20)


# --- Splits par km -----------------------------------------------------------------------------


def test_km_splits_interpolate_boundaries() -> None:
    # 2,5 km à 4 m/s, 1 point toutes les 50 m (12,5 s).
    points = [point(i, i * 12.5, i * 50.0) for i in range(51)]
    splits, trace = metrics.km_splits(points, None, None)
    assert [(s["start_distance_m"], s["end_distance_m"]) for s in splits] == [
        (0.0, 1000.0),
        (1000.0, 2000.0),
        (2000.0, 2500.0),
    ]
    assert [s["duration_s"] for s in splits] == pytest.approx([250.0, 250.0, 125.0])
    assert all(s["kind"] == LapKind.km for s in splits)
    assert splits[0]["avg_hr"] == 150
    assert trace["method"] == "interpolated_km_splits"


def test_km_splits_elevation_follows_profile_scaled_to_garmin_total() -> None:
    # 1er km : +20 m, 2e km : -10 m (altitude lue tous les 100 m).
    alts = [100, 104, 108, 112, 116, 120, 120, 120, 120, 120, 120]
    alts += [118, 116, 114, 112, 110, 110, 110, 110, 110, 110]
    points = [point(i, i * 30.0, i * 100.0, alt=a) for i, a in enumerate(alts)]
    splits, trace = metrics.km_splits(points, total_gain_m=40.0, total_loss_m=10.0)
    assert [s["elevation_gain_m"] for s in splits] == [40.0, 0.0]
    assert [s["elevation_loss_m"] for s in splits] == [0.0, 10.0]
    assert trace["inputs"]["fit_gain_m"] == 20.0


def test_km_splits_ignore_altitude_noise_below_threshold() -> None:
    alts = [100.0, 100.4, 99.8, 100.3, 99.9, 100.2] * 3
    points = [point(i, float(i), i * 10.0, alt=a) for i, a in enumerate(alts)]
    splits, _ = metrics.km_splits(points, None, None)
    assert splits[0]["elevation_gain_m"] == 0.0


def test_km_splits_use_timer_time_without_pauses() -> None:
    # 2 km à 4 m/s ; 120 s de pause au km 0,5 : temps écoulé décalé, chrono non.
    points = [
        point(i, i * 12.5 + (120 if i > 10 else 0), i * 50.0, timer=i * 12.5) for i in range(41)
    ]
    splits, trace = metrics.km_splits(points, None, None)
    assert [s["duration_s"] for s in splits] == pytest.approx([250.0, 250.0])
    assert trace["params"]["time"] == "timer_excluding_pauses"


def test_km_splits_without_points() -> None:
    assert metrics.km_splits([], 10.0, 10.0)[0] == []


# --- Calcul complet, recalcul et réglages ------------------------------------------------------


def _activity(db: Session, user: User, gain: float = 400.0) -> Activity:
    activity = activities.activity_from_summary(user.id, summary(1))
    activity.distance_m, activity.elevation_gain_m = 10000.0, gain
    db.add(activity)
    db.flush()
    db.add_all([point(i, i * 12.5, i * 50.0) for i in range(41)])
    for p in db.new:
        if isinstance(p, ActivityPoint):
            p.activity_id = activity.id
    db.commit()
    return activity


def test_compute_stores_category_effort_splits_and_trace(db: Session, admin: User) -> None:
    activity = _activity(db, admin)
    metrics.compute(db, activity)
    db.commit()
    assert activity.category == "short_trail"
    assert activity.km_effort == 14.0
    assert activity.calc_trace is not None
    assert activity.calc_trace["version"] == metrics.METRICS_VERSION
    splits = db.scalars(select(ActivityLap).where(ActivityLap.kind == LapKind.km)).all()
    assert len(splits) == 2

    # Recalculer remplace les splits.
    metrics.compute(db, activity)
    db.commit()
    assert len(db.scalars(select(ActivityLap).where(ActivityLap.kind == LapKind.km)).all()) == 2


def test_admin_settings_defaults_and_partial_update(admin_client: TestClient, db: Session) -> None:
    defaults = admin_client.get("/api/admin/settings").json()
    assert defaults["activity_categories"] == {
        "road_max_dplus_per_km": 10,
        "trail_min_dplus_per_km": 25,
        "long_trail_min_km_effort": 42,
    }
    response = admin_client.put(
        "/api/admin/settings", json={"activity_categories": {"trail_min_dplus_per_km": 30}}
    )
    assert response.status_code == 200
    updated = response.json()["activity_categories"]
    assert updated["trail_min_dplus_per_km"] == 30
    assert updated["road_max_dplus_per_km"] == 10
    # Changer un seuil met en file le recalcul de toutes les activités.
    assert db.scalar(select(Job).where(Job.type == "recompute_metrics")) is not None


def test_admin_settings_validation(admin_client: TestClient) -> None:
    bad_order = {"activity_categories": {"road_max_dplus_per_km": 40}}
    response = admin_client.put("/api/admin/settings", json=bad_order)
    assert response.status_code == 422
    assert "seuil route" in response.json()["detail"]
    unknown_key = admin_client.put("/api/admin/settings", json={"nope": {}})
    assert unknown_key.status_code == 422
    unknown_field = {"activity_categories": {"typo": 1}}
    assert admin_client.put("/api/admin/settings", json=unknown_field).status_code == 422


def test_unchanged_settings_do_not_trigger_recompute(admin_client: TestClient, db: Session) -> None:
    admin_client.put("/api/admin/settings", json={"activity_categories": {}})
    assert db.scalar(select(Job).where(Job.type == "recompute_metrics")) is None


def test_settings_are_admin_only(client: TestClient, db: Session) -> None:
    make_user(db, "bob@example.com")
    login(client, "bob@example.com")
    assert client.get("/api/admin/settings").status_code == 403


def test_recompute_task_applies_new_thresholds(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    activity = _activity(db, admin, gain=150.0)  # 15 m/km
    metrics.compute(db, activity)
    db.commit()
    assert activity.category == "mixed"

    admin_client.put(
        "/api/admin/settings", json={"activity_categories": {"road_max_dplus_per_km": 20}}
    )
    while jobs.run_one():
        pass
    db.refresh(activity)
    assert activity.category == "road"
