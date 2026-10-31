from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Le .env est à la racine du monorepo.
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://runningstats:runningstats@localhost:5433/runningstats"


@lru_cache
def get_settings() -> Settings:
    return Settings()
