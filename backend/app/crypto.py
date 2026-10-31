"""Chiffrement des secrets stockés en base (clés et jetons Garmin).

La clé maître vient de la variable d'environnement GARMIN_ENCRYPTION_KEY, jamais de la base.
Générer une clé :
    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


class MissingEncryptionKey(RuntimeError):
    pass


@lru_cache
def _fernet(key: str) -> Fernet:
    return Fernet(key)


def _current() -> Fernet:
    key = get_settings().garmin_encryption_key
    if not key:
        raise MissingEncryptionKey(
            "GARMIN_ENCRYPTION_KEY n'est pas définie : impossible de chiffrer les secrets Garmin."
        )
    return _fernet(key)


def encrypt(value: str) -> str:
    return _current().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _current().decrypt(value.encode()).decode()
