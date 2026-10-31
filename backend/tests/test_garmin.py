import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto, garmin
from app.models import GarminAccount, GarminStatus, User
from app.security import utcnow

API_KEY = "my-secret-garmin-key"


def fake_jwt(expires_at: datetime) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part({'exp': int(expires_at.timestamp())})}.sig"


class FakeGarmin:
    """Remplace le service de jetons de Garmin : aucun appel réseau dans les tests."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None

    def __call__(self, api_key: str) -> str:
        self.calls.append(api_key)
        if self.error:
            raise self.error
        return fake_jwt(utcnow() + timedelta(hours=24))


@pytest.fixture
def fake_garmin(monkeypatch: pytest.MonkeyPatch) -> FakeGarmin:
    fake = FakeGarmin()
    monkeypatch.setattr(garmin, "_request_token", fake)
    return fake


def account_of(db: Session, user: User) -> GarminAccount | None:
    db.expire_all()
    return db.scalar(select(GarminAccount).where(GarminAccount.user_id == user.id))


def test_requires_login(client: TestClient) -> None:
    assert client.get("/api/me/garmin").status_code == 401
    assert client.put("/api/me/garmin", json={"api_key": API_KEY}).status_code == 401


def test_not_connected_by_default(admin_client: TestClient) -> None:
    assert admin_client.get("/api/me/garmin").json()["connected"] is False


def test_save_key_tests_it_and_stores_it_encrypted(
    admin_client: TestClient, admin: User, db: Session, fake_garmin: FakeGarmin
) -> None:
    response = admin_client.put(
        "/api/me/garmin", json={"api_key": f"  {API_KEY}\n", "api_key_expires_on": "2027-04-30"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["connected"] is True
    assert body["status"] == "ok"
    assert body["source"] == "personal_api"
    assert body["api_key_expires_at"].startswith("2027-04-30")
    assert fake_garmin.calls == [API_KEY]

    account = account_of(db, admin)
    assert account is not None
    assert API_KEY not in (account.api_key_encrypted or "")
    assert crypto.decrypt(account.api_key_encrypted or "") == API_KEY
    assert account.token_expires_at is not None
    # La réponse ne contient jamais la clé ni le jeton.
    assert API_KEY not in response.text and "token" not in response.text


def test_rejected_key_is_not_saved(
    admin_client: TestClient, admin: User, db: Session, fake_garmin: FakeGarmin
) -> None:
    fake_garmin.error = garmin.GarminKeyRejected("HTTP 401")
    response = admin_client.put("/api/me/garmin", json={"api_key": API_KEY})
    assert response.status_code == 400
    assert "refusé" in response.json()["detail"]
    assert account_of(db, admin) is None


def test_garmin_down_gives_502(admin_client: TestClient, fake_garmin: FakeGarmin) -> None:
    fake_garmin.error = garmin.GarminUnavailable("HTTP 503")
    assert admin_client.put("/api/me/garmin", json={"api_key": API_KEY}).status_code == 502


def test_new_key_replaces_old_one_and_clears_error(
    admin_client: TestClient, admin: User, db: Session, fake_garmin: FakeGarmin
) -> None:
    admin_client.put("/api/me/garmin", json={"api_key": "old-key"})
    account = account_of(db, admin)
    assert account is not None
    account.status, account.last_error = GarminStatus.error, "boom"
    db.commit()

    admin_client.put("/api/me/garmin", json={"api_key": "new-key"})
    account = account_of(db, admin)
    assert account is not None
    assert crypto.decrypt(account.api_key_encrypted or "") == "new-key"
    assert account.status == GarminStatus.ok and account.last_error is None


def test_disconnect(
    admin_client: TestClient, admin: User, db: Session, fake_garmin: FakeGarmin
) -> None:
    admin_client.put("/api/me/garmin", json={"api_key": API_KEY})
    assert admin_client.delete("/api/me/garmin").status_code == 204
    assert account_of(db, admin) is None
    assert admin_client.get("/api/me/garmin").json()["connected"] is False


def test_key_expires_soon_flag(admin_client: TestClient, fake_garmin: FakeGarmin) -> None:
    soon = (utcnow() + timedelta(days=3)).date().isoformat()
    later = (utcnow() + timedelta(days=60)).date().isoformat()
    body = {"api_key": API_KEY, "api_key_expires_on": soon}
    assert admin_client.put("/api/me/garmin", json=body).json()["key_expires_soon"] is True
    body["api_key_expires_on"] = later
    assert admin_client.put("/api/me/garmin", json=body).json()["key_expires_soon"] is False


def _account(db: Session, user: User, token_expires_in: timedelta) -> GarminAccount:
    account = GarminAccount(user_id=user.id, api_key_encrypted=crypto.encrypt(API_KEY))
    garmin.store_token(account, "cached-token", utcnow() + token_expires_in)
    db.add(account)
    db.commit()
    return account


def test_ensure_token_reuses_a_fresh_token(
    db: Session, admin: User, fake_garmin: FakeGarmin
) -> None:
    account = _account(db, admin, timedelta(hours=5))
    assert garmin.ensure_token(db, account) == "cached-token"
    assert fake_garmin.calls == []


def test_ensure_token_renews_a_token_expiring_within_an_hour(
    db: Session, admin: User, fake_garmin: FakeGarmin
) -> None:
    account = _account(db, admin, timedelta(minutes=30))
    token = garmin.ensure_token(db, account)
    assert token != "cached-token"
    assert fake_garmin.calls == [API_KEY]
    assert account.token_expires_at is not None
    assert account.token_expires_at > utcnow() + timedelta(hours=23)


def test_ensure_token_marks_expired_key(db: Session, admin: User, fake_garmin: FakeGarmin) -> None:
    account = _account(db, admin, timedelta(minutes=-1))
    account.api_key_expires_at = datetime(2020, 1, 1, tzinfo=UTC)
    fake_garmin.error = garmin.GarminKeyRejected("HTTP 401")
    with pytest.raises(garmin.GarminKeyRejected):
        garmin.ensure_token(db, account)
    assert account.status == GarminStatus.key_expired


def test_ensure_token_marks_error_when_key_refused(
    db: Session, admin: User, fake_garmin: FakeGarmin
) -> None:
    account = _account(db, admin, timedelta(minutes=-1))
    fake_garmin.error = garmin.GarminKeyRejected("HTTP 401")
    with pytest.raises(garmin.GarminKeyRejected):
        garmin.ensure_token(db, account)
    assert account.status == GarminStatus.error
    assert account.last_error
