from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Le .env est à la racine du monorepo.
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://runningstats:runningstats@localhost:5433/runningstats"

    # Accès
    max_members: int = 5
    session_days: int = 30
    invitation_days: int = 7
    session_cookie_name: str = "rs_session"
    # True en production (HTTPS) ; False en dev sur http://localhost.
    session_cookie_secure: bool = False

    # Clé maître (Fernet) qui chiffre les clés et jetons Garmin en base. Voir app/crypto.py.
    garmin_encryption_key: str = ""

    # Tâches de fond
    # Fuseau du groupe : sert aux horaires du planificateur (maintenance à 3 h, pause de nuit…).
    timezone: str = "Europe/Paris"
    worker_poll_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
