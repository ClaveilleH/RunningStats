"""Les tests tournent sur une base dédiée <nom>_test, créée et migrée automatiquement."""

import os
import tempfile
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings

# À faire avant tout import de app.db, qui crée le moteur à l'import.
_dev_url = make_url(get_settings().database_url)
TEST_URL = _dev_url.set(database=f"{_dev_url.database}_test")
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
# Clé de chiffrement propre aux tests, indépendante du .env.
os.environ["GARMIN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
# Fichiers FIT des tests dans un dossier temporaire.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="runningstats-tests-")
get_settings.cache_clear()

from datetime import timedelta  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import accounts, crypto, garmin  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GarminAccount, Role, User  # noqa: E402
from app.security import utcnow  # noqa: E402
from tests.garmin_fakes import FakeGarminApi  # noqa: E402

PASSWORD = "correct-horse-battery"


def _create_test_database() -> None:
    admin_engine = create_engine(_dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_URL.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    _create_test_database()
    # Les tests passent par les vraies migrations, pas par create_all.
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_user(db: Session, email: str, role: Role = Role.member) -> User:
    user = accounts.create_user(
        db, display_name=email.split("@")[0], email=email, password=PASSWORD, role=role
    )
    db.commit()
    return user


def login(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


@pytest.fixture
def admin(db: Session) -> User:
    return make_user(db, "admin@example.com", Role.admin)


@pytest.fixture
def admin_client(client: TestClient, admin: User) -> TestClient:
    login(client, admin.email)
    return client


# Faux Garmin et compte connecté, pour les tests de synchro.
@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeGarminApi:
    fake = FakeGarminApi()
    monkeypatch.setattr(garmin, "GarminPersonalApiClient", fake.client)
    monkeypatch.setattr(garmin, "_throttle", lambda: None)
    monkeypatch.setattr(garmin, "_request_token", lambda key: _jwt())
    return fake


def _jwt() -> str:
    from tests.test_garmin import fake_jwt

    return fake_jwt(utcnow() + timedelta(hours=24))


@pytest.fixture
def account(db: Session, admin: User) -> GarminAccount:
    account = GarminAccount(user_id=admin.id, api_key_encrypted=crypto.encrypt("key"))
    garmin.store_token(account, "token", utcnow() + timedelta(hours=10))
    db.add(account)
    db.commit()
    return account
