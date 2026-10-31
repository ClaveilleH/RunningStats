from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invitation
from app.security import MIN_PASSWORD_LENGTH, utcnow
from tests.conftest import make_user

NEW_MEMBER = {"display_name": "Alice", "email": "alice@example.com", "password": "alice-password"}


def invite(admin_client: TestClient) -> str:
    response = admin_client.post("/api/admin/invitations")
    assert response.status_code == 201, response.text
    return response.json()["token"]


def test_invitation_flow(admin_client: TestClient, db: Session) -> None:
    token = invite(admin_client)
    # Le jeton en clair n'est pas en base.
    assert db.scalar(select(Invitation.token_hash)) != token

    guest = TestClient(admin_client.app)
    assert guest.get(f"/api/auth/invitations/{token}").json()["valid"] is True

    created = guest.post(f"/api/auth/invitations/{token}", json=NEW_MEMBER)
    assert created.status_code == 201
    assert created.json()["role"] == "member"
    # Connecté directement après création du compte.
    assert guest.get("/api/me").json()["email"] == "alice@example.com"

    # Le lien ne sert qu'une fois.
    assert guest.get(f"/api/auth/invitations/{token}").status_code == 404
    again = {**NEW_MEMBER, "email": "alice2@example.com"}
    assert guest.post(f"/api/auth/invitations/{token}", json=again).status_code == 404


def test_unknown_and_expired_invitations(admin_client: TestClient, db: Session) -> None:
    assert admin_client.get("/api/auth/invitations/nope").status_code == 404

    token = invite(admin_client)
    invitation = db.scalar(select(Invitation))
    assert invitation is not None
    invitation.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert admin_client.get(f"/api/auth/invitations/{token}").status_code == 404


def test_short_password_rejected(admin_client: TestClient) -> None:
    token = invite(admin_client)
    body = {**NEW_MEMBER, "password": "short"}
    assert admin_client.post(f"/api/auth/invitations/{token}", json=body).status_code == 422


def test_duplicate_email_rejected(admin_client: TestClient, db: Session) -> None:
    make_user(db, "alice@example.com")
    token = invite(admin_client)
    response = admin_client.post(f"/api/auth/invitations/{token}", json=NEW_MEMBER)
    assert response.status_code == 409


def test_group_limited_to_five_members(admin_client: TestClient, db: Session) -> None:
    for name in ("b", "c", "d"):
        make_user(db, f"{name}@example.com")
    # 4 membres : une seule invitation possible.
    invite(admin_client)
    response = admin_client.post("/api/admin/invitations")
    assert response.status_code == 409
    assert "5 membres maximum" in response.json()["detail"]


def test_invitation_check_gives_password_rule(admin_client: TestClient) -> None:
    token = invite(admin_client)
    check = admin_client.get(f"/api/auth/invitations/{token}").json()
    assert check["min_password_length"] == MIN_PASSWORD_LENGTH


def test_password_rule_message_is_french(admin_client: TestClient) -> None:
    token = invite(admin_client)
    too_short = "x" * (MIN_PASSWORD_LENGTH - 1)
    body = {**NEW_MEMBER, "password": too_short}
    issue = admin_client.post(f"/api/auth/invitations/{token}", json=body).json()["detail"][0]
    assert issue["type"] == "password_too_short"
    assert issue["msg"] == f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères."

    body["password"] = "x" * MIN_PASSWORD_LENGTH
    assert admin_client.post(f"/api/auth/invitations/{token}", json=body).status_code == 201
