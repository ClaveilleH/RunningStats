from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.tasks  # noqa: F401  (enregistre les tâches)
from app import races, sync_schedule
from app.models import GarminAccount, RaceParticipant, User
from tests.conftest import login, make_user
from tests.garmin_fakes import FakeGarminApi, summary
from tests.test_activities import add
from tests.test_sync import sync

TODAY = date(2026, 10, 31)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(races, "today", lambda: TODAY)


def race_body(**changes: object) -> dict:
    body = {
        "name": "Trail des Baous",
        "date": "2026-11-07",
        "start_time": "08:30",
        "location": "Saint-Jeannet",
        "distance_m": 23000,
        "elevation_gain_m": 1250,
        "official_url": "https://trail-baous.example.com",
    }
    return {**body, **changes}


def create(client: TestClient, **changes: object) -> dict:
    response = client.post("/api/races", json=race_body(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_computes_category_and_effort(admin_client: TestClient, admin: User) -> None:
    race = create(admin_client)
    assert race["category"] == "short_trail"  # 54 m/km, 35,5 km-effort
    assert race["km_effort"] == 35.5
    assert race["created_by_name"] == admin.display_name
    assert race["can_edit"] is True
    assert race["joined"] is False
    road = create(admin_client, name="Semi", distance_m=21100, elevation_gain_m=90)
    assert road["category"] == "road"


def test_invalid_race_is_refused(admin_client: TestClient) -> None:
    assert admin_client.post("/api/races", json=race_body(distance_m=0)).status_code == 422
    assert admin_client.post("/api/races", json=race_body(name="")).status_code == 422
    bad_url = race_body(official_url="pas une url")
    assert admin_client.post("/api/races", json=bad_url).status_code == 422


def test_upcoming_and_past_lists(admin_client: TestClient) -> None:
    create(admin_client, name="Plus tard", date="2027-01-16")
    create(admin_client, name="Bientôt", date="2026-11-07")
    create(admin_client, name="Aujourd'hui", date="2026-10-31")
    create(admin_client, name="Passée", date="2026-10-11")
    create(admin_client, name="Très ancienne", date="2025-05-01")
    upcoming = [r["name"] for r in admin_client.get("/api/races").json()]
    assert upcoming == ["Aujourd'hui", "Bientôt", "Plus tard"]
    past = [r["name"] for r in admin_client.get("/api/races?past=true").json()]
    assert past == ["Passée", "Très ancienne"]
    window = admin_client.get("/api/races?from=2026-11-01&to=2026-12-31").json()
    assert [r["name"] for r in window] == ["Bientôt"]
    trails = admin_client.get("/api/races?category=road").json()
    assert trails == []


def test_join_and_leave(admin_client: TestClient, admin: User) -> None:
    race = create(admin_client)
    joined = admin_client.post(f"/api/races/{race['id']}/participation").json()
    assert joined["joined"] is True
    assert [p["display_name"] for p in joined["participants"]] == [admin.display_name]
    # Deux fois « J'y vais » ne crée pas de doublon.
    again = admin_client.post(f"/api/races/{race['id']}/participation").json()
    assert len(again["participants"]) == 1
    left = admin_client.delete(f"/api/races/{race['id']}/participation").json()
    assert left["joined"] is False and left["participants"] == []


def test_friends_see_the_list_but_only_author_or_admin_edits(
    client: TestClient, db: Session, admin: User
) -> None:
    bob = make_user(db, "bob@example.com")
    login(client, bob.email)
    race = create(client)
    client.post(f"/api/races/{race['id']}/participation")
    client.post("/api/auth/logout")

    lea = make_user(db, "lea@example.com")
    login(client, lea.email)
    seen = client.get("/api/races").json()[0]
    assert seen["can_edit"] is False
    assert [p["display_name"] for p in seen["participants"]] == ["bob"]
    assert seen["participants"][0]["activity_id"] is None
    assert client.put(f"/api/races/{race['id']}", json=race_body()).status_code == 403
    assert client.delete(f"/api/races/{race['id']}").status_code == 403
    client.post("/api/auth/logout")

    login(client, admin.email)  # l'admin peut tout modifier
    updated = client.put(f"/api/races/{race['id']}", json=race_body(name="Baous 2026"))
    assert updated.json()["name"] == "Baous 2026"
    assert client.delete(f"/api/races/{race['id']}").status_code == 204
    assert client.get(f"/api/races/{race['id']}").status_code == 404


def test_joining_a_past_race_links_the_activity(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    race = create(admin_client, date="2026-10-11", distance_m=15400, elevation_gain_m=820)
    add(db, admin, date(2026, 10, 11), name="Footing du matin", km=5)
    run = add(db, admin, date(2026, 10, 11), name="Pic de l'Ours", km=16.2)  # +5 %
    add(db, admin, date(2026, 10, 12), name="Lendemain", km=15.4)
    body = admin_client.post(f"/api/races/{race['id']}/participation").json()
    assert body["participants"][0]["activity_id"] == run.id
    listed = admin_client.get(f"/api/users/{admin.id}/activities").json()["items"]
    badges = {i["name"]: i["race"] for i in listed}
    assert badges["Pic de l'Ours"] == {"id": race["id"], "name": "Trail des Baous"}
    assert badges["Lendemain"] is None


def test_too_different_distance_is_not_linked(
    admin_client: TestClient, db: Session, admin: User
) -> None:
    race = create(admin_client, date="2026-10-11", distance_m=15400)
    add(db, admin, date(2026, 10, 11), km=12)  # −22 %
    body = admin_client.post(f"/api/races/{race['id']}/participation").json()
    assert body["participants"][0]["activity_id"] is None


def test_new_activity_is_linked_by_the_sync(
    admin_client: TestClient,
    db: Session,
    admin: User,
    api: FakeGarminApi,
    account: GarminAccount,
) -> None:
    # La course du 25/10, et la sortie de 10 km de ce jour-là synchronisée ensuite.
    race = create(admin_client, date="2026-10-25", distance_m=10000, elevation_gain_m=100)
    admin_client.post(f"/api/races/{race['id']}/participation")
    api.activities = [summary(1)]
    sync(db, admin)
    participant = db.scalars(select(RaceParticipant)).one()
    assert participant.activity_id is not None


def test_race_day_speeds_up_the_sync(admin_client: TestClient, db: Session, admin: User) -> None:
    race = create(admin_client, date="2026-10-31")
    noon = datetime(2026, 10, 31, 12, tzinfo=UTC)
    assert not sync_schedule.is_race_day(db, admin.id, noon)
    admin_client.post(f"/api/races/{race['id']}/participation")
    assert sync_schedule.is_race_day(db, admin.id, noon)
