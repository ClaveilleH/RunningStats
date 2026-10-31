from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import activity_list
from app.models import Activity, ActivityPoint, User
from tests.conftest import make_user

_next_id = iter(range(1, 10_000))


def add(
    db: Session,
    user: User,
    day: date,
    *,
    name: str = "Footing",
    km: float = 10,
    dplus: float = 100,
    duration_s: float = 3000,
    category: str = "road",
    location: str | None = "Mougins",
) -> Activity:
    start = datetime(day.year, day.month, day.day, 8, 0)
    activity = Activity(
        user_id=user.id,
        garmin_id=next(_next_id),
        activity_type="running",
        name=name,
        start_time=start.replace(tzinfo=UTC) - timedelta(hours=1),
        start_time_local=start,
        distance_m=km * 1000,
        duration_s=duration_s,
        elevation_gain_m=dplus,
        avg_hr=150,
        category=category,
        location_name=location,
        raw_summary={},
    )
    db.add(activity)
    db.commit()
    return activity


def url(user: User, query: str = "") -> str:
    return f"/api/users/{user.id}/activities{query}"


def test_list_newest_first_with_pace_and_summary(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    add(db, admin, date(2026, 10, 1), name="Ancienne", km=5, duration_s=1500)
    add(db, admin, date(2026, 10, 20), name="Récente", km=10, duration_s=3300)
    body = admin_client.get(url(admin)).json()
    assert [i["name"] for i in body["items"]] == ["Récente", "Ancienne"]
    assert body["items"][0]["pace_s_per_km"] == 330
    assert body["items"][0]["track"] is None
    assert body["total"] == 2
    assert body["summary"] == {
        "count": 2,
        "distance_m": 15000,
        "elevation_gain_m": 200,
        "duration_s": 4800,
    }


def test_filters_apply_to_items_and_summary(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    add(db, admin, date(2026, 9, 1), name="Baous", category="short_trail", location="Vence")
    add(db, admin, date(2026, 10, 2), name="Côte de Valbonne", category="mixed")
    add(db, admin, date(2026, 10, 3), name="Footing", category="road", location="Valbonne")

    def names(query: str) -> list[str]:
        return [i["name"] for i in admin_client.get(url(admin, query)).json()["items"]]

    assert names("?category=short_trail") == ["Baous"]
    assert names("?q=valbonne") == ["Footing", "Côte de Valbonne"]  # nom ou lieu
    assert names("?from=2026-10-01&to=2026-10-02") == ["Côte de Valbonne"]
    body = admin_client.get(url(admin, "?q=vence")).json()
    assert body["summary"]["count"] == 1
    assert admin_client.get(url(admin, "?category=velo")).status_code == 422


def test_sort_and_pagination(admin_client: TestClient, db: Session, admin: User) -> None:
    for i, km in enumerate([8, 21, 12]):
        add(db, admin, date(2026, 10, 1 + i), name=f"S{km}", km=km)
    body = admin_client.get(url(admin, "?sort=distance&page_size=2")).json()
    assert [i["name"] for i in body["items"]] == ["S21", "S12"]
    assert body["total"] == 3
    page2 = admin_client.get(url(admin, "?sort=distance&page_size=2&page=2")).json()
    assert [i["name"] for i in page2["items"]] == ["S8"]
    asc = admin_client.get(url(admin, "?sort=distance&order=asc")).json()
    assert asc["items"][0]["name"] == "S8"


def test_track_preview_is_sampled(admin_client: TestClient, db: Session, admin: User) -> None:
    activity = add(db, admin, date(2026, 10, 1))
    db.add_all(
        ActivityPoint(activity_id=activity.id, seq=i, t_s=i, lat=45 + i * 1e-5, lon=6.0)
        for i in range(600)
    )
    db.commit()
    track = admin_client.get(url(admin, "?with_track=true")).json()["items"][0]["track"]
    assert 55 <= len(track) <= 62
    assert track[0] == [45.0, 6.0]
    assert track[-1][0] == round(45 + 599e-5, 5)  # le dernier point est gardé


def test_only_own_activities_for_now(admin_client: TestClient, db: Session) -> None:
    bob = make_user(db, "bob@example.com")
    add(db, bob, date(2026, 10, 1))
    assert admin_client.get(url(bob)).status_code == 403
    assert admin_client.get(url(bob, "/weekly")).status_code == 403
    assert admin_client.get("/api/users/999/activities").status_code == 404


def test_requires_login(client: TestClient, db: Session, admin: User) -> None:
    assert client.get(url(admin)).status_code == 401


def test_weekly_fills_empty_weeks(db: Session, admin: User) -> None:
    add(db, admin, date(2026, 10, 12), km=10, dplus=300)  # lundi
    add(db, admin, date(2026, 10, 18), km=5, dplus=50)  # dimanche, même semaine
    add(db, admin, date(2026, 10, 27), km=8)  # semaine en cours
    add(db, admin, date(2026, 9, 1), km=30)  # trop ancienne
    weeks = activity_list.weekly(db, admin.id, 4, today=date(2026, 10, 31))
    assert [w["week_start"] for w in weeks] == [
        date(2026, 10, 5),
        date(2026, 10, 12),
        date(2026, 10, 19),
        date(2026, 10, 26),
    ]
    assert [w["distance_m"] for w in weeks] == [0, 15000, 0, 8000]
    assert weeks[1]["elevation_gain_m"] == 350
    assert weeks[1]["count"] == 2
    assert [w["current"] for w in weeks] == [False, False, False, True]


def test_weekly_route(admin_client: TestClient, admin: User) -> None:
    weeks = admin_client.get(url(admin, "/weekly?weeks=12")).json()
    assert len(weeks) == 12
    assert weeks[-1]["current"] is True
