from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from tests.conftest import PASSWORD, login, make_user


def test_login_sets_httponly_cookie_and_me_works(client: TestClient, admin: User) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "ADMIN@example.com ", "password": PASSWORD}
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert get_settings().session_cookie_name in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    me = client.get("/api/me").json()
    assert me["email"] == "admin@example.com"
    assert me["role"] == "admin"
    assert "password_hash" not in me


def test_login_rejects_bad_password_and_unknown_email(client: TestClient, admin: User) -> None:
    bad = client.post("/api/auth/login", json={"email": admin.email, "password": "wrong-pass"})
    unknown = client.post("/api/auth/login", json={"email": "x@example.com", "password": PASSWORD})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


def test_routes_require_login(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/admin/invitations").status_code == 401


def test_logout_closes_session(admin_client: TestClient) -> None:
    assert admin_client.post("/api/auth/logout").status_code == 204
    assert admin_client.get("/api/me").status_code == 401


def test_member_cannot_use_admin_routes(client: TestClient, db: Session) -> None:
    make_user(db, "bob@example.com")
    login(client, "bob@example.com")
    assert client.post("/api/admin/invitations").status_code == 403


def test_change_password(admin_client: TestClient, admin: User) -> None:
    wrong = admin_client.put(
        "/api/me/password",
        json={"current_password": "nope-nope-nope", "new_password": "new-password-123"},
    )
    assert wrong.status_code == 400

    ok = admin_client.put(
        "/api/me/password",
        json={"current_password": PASSWORD, "new_password": "new-password-123"},
    )
    assert ok.status_code == 204
    # La session en cours reste ouverte.
    assert admin_client.get("/api/me").status_code == 200

    other = TestClient(admin_client.app)
    assert (
        other.post("/api/auth/login", json={"email": admin.email, "password": PASSWORD}).status_code
        == 401
    )
    login(other, admin.email, "new-password-123")


def test_change_password_logs_out_other_devices(client: TestClient, admin: User) -> None:
    login(client, admin.email)
    other = TestClient(client.app)
    login(other, admin.email)

    client.put(
        "/api/me/password",
        json={"current_password": PASSWORD, "new_password": "new-password-123"},
    )
    assert other.get("/api/me").status_code == 401
