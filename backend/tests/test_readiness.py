from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DailyHealth, SleepNight, User
from tests.conftest import make_user
from tests.test_activities import add

# Sortie du samedi 24/10/2026 à 8 h (heure de la montre), 7 h UTC.
RUN_DAY = date(2026, 10, 24)


def night(db: Session, user: User, day: date, score: int | None, hours: float = 7) -> None:
    db.add(
        SleepNight(
            user_id=user.id,
            date=day,
            end_time=datetime(day.year, day.month, day.day, 5, 30, tzinfo=UTC),
            total_s=int(hours * 3600),
            score=score,
            raw={},
        )
    )


def health(db: Session, user: User, day: date, resting_hr: int, battery: int = 70) -> None:
    db.add(DailyHealth(user_id=user.id, date=day, resting_hr=resting_hr, body_battery_max=battery))


def readiness(client: TestClient, activity_id: int) -> dict:
    response = client.get(f"/api/activities/{activity_id}/readiness")
    assert response.status_code == 200, response.text
    return response.json()


def test_sleep_score_weights_the_last_night_most(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    activity = add(db, admin, RUN_DAY)
    night(db, admin, date(2026, 10, 24), 60, hours=6)  # veille : 50 %
    night(db, admin, date(2026, 10, 23), 80)  # 30 %
    night(db, admin, date(2026, 10, 22), 90)  # 20 %
    db.commit()
    body = readiness(admin_client, activity.id)
    assert body["sleep_score"] == 72  # 60×0,5 + 80×0,3 + 90×0,2
    assert [n["date"] for n in body["nights"]] == ["2026-10-24", "2026-10-23", "2026-10-22"]
    assert body["nights"][0]["total_s"] == 6 * 3600
    assert body["trace"]["params"]["sleep_weights"] == [50, 30, 20]


def test_missing_night_rescales_weights(admin_client: TestClient, db: Session, admin: User) -> None:
    activity = add(db, admin, RUN_DAY)
    night(db, admin, date(2026, 10, 24), 60)
    night(db, admin, date(2026, 10, 22), 90)
    db.commit()
    body = readiness(admin_client, activity.id)
    assert body["sleep_score"] == round((60 * 50 + 90 * 20) / 70)
    assert body["nights"][1]["score"] is None
    assert body["trace"]["inputs"]["sleep_weight_used"] == 70


def test_run_during_the_night_uses_previous_nights(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    activity = add(db, admin, RUN_DAY)
    activity.start_time = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)  # avant le réveil
    night(db, admin, date(2026, 10, 24), 40)
    night(db, admin, date(2026, 10, 23), 80)
    db.commit()
    body = readiness(admin_client, activity.id)
    assert body["nights"][0]["date"] == "2026-10-23"


def test_resting_hr_against_previous_week_and_body_battery(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    activity = add(db, admin, RUN_DAY)
    for d in range(17, 24):  # 7 jours d'avant
        health(db, admin, date(2026, 10, d), 50 + (d % 2))
    health(db, admin, date(2026, 10, 10), 70)  # trop ancien, ignoré
    health(db, admin, RUN_DAY, 54, battery=68)
    db.commit()
    body = readiness(admin_client, activity.id)
    assert body["resting_hr"] == 54
    assert body["resting_hr_baseline"] == round((50 * 3 + 51 * 4) / 7, 1)
    assert body["resting_hr_delta"] == 3
    assert body["body_battery_max"] == 68


def test_without_health_data(admin_client: TestClient, db: Session, admin: User) -> None:
    activity = add(db, admin, RUN_DAY)
    body = readiness(admin_client, activity.id)
    assert body["sleep_score"] is None
    assert body["resting_hr"] is None
    assert body["resting_hr_delta"] is None
    assert len(body["nights"]) == 3


def test_weights_are_an_admin_setting(admin_client: TestClient, db: Session, admin: User) -> None:
    rules = {"readiness": {"sleep_weights": [100], "resting_hr_baseline_days": 7}}
    assert admin_client.put("/api/admin/settings", json=rules).status_code == 200
    activity = add(db, admin, RUN_DAY)
    night(db, admin, date(2026, 10, 24), 60)
    night(db, admin, date(2026, 10, 23), 100)
    db.commit()
    body = readiness(admin_client, activity.id)
    assert body["sleep_score"] == 60
    bad = {"readiness": {"sleep_weights": [0, 0]}}
    assert admin_client.put("/api/admin/settings", json=bad).status_code == 422


def test_other_members_readiness_is_not_found(admin_client: TestClient, db: Session) -> None:
    bob = make_user(db, "bob@example.com")
    activity = add(db, bob, RUN_DAY)
    assert admin_client.get(f"/api/activities/{activity.id}/readiness").status_code == 404
