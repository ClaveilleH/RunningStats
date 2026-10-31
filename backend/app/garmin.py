"""Accès à l'API personnelle Garmin : échange de la clé contre un jeton 24 h, client de lecture.

S'appuie sur la bibliothèque officielle garmin-connect-personal-api-python pour les lectures.
L'échange de la clé est fait ici plutôt qu'avec PersonalApiAuthenticator, qui met le jeton
en cache dans un fichier : chez nous il est stocké chiffré en base.
"""

import base64
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from garmin_personal_api import GarminPersonalApiClient, HttpError
from garmin_personal_api.constants import BASE_URL_ENV_VAR, DEFAULT_BASE_URL, TOKEN_PATH
from sqlalchemy.orm import Session

from app import crypto
from app.models import GarminAccount, GarminStatus
from app.security import utcnow

TIMEOUT_SECONDS = 30
# Un jeton qui expire dans moins d'1 h est renouvelé avant l'appel.
TOKEN_REFRESH_MARGIN = timedelta(hours=1)
# La clé expire bientôt : prévenir le membre (bandeau dans Réglages).
KEY_EXPIRY_WARNING = timedelta(days=7)
# Doc : 0,5 s entre deux requêtes vers Garmin.
MIN_SECONDS_BETWEEN_REQUESTS = 0.5


class GarminKeyRejected(Exception):
    """Garmin refuse la clé (401 / 403) : clé fausse, révoquée ou expirée."""


class GarminUnavailable(Exception):
    """Garmin injoignable, erreur 5xx ou trop de requêtes (429) : réessayer plus tard."""


def base_url() -> str:
    return os.environ.get(BASE_URL_ENV_VAR, DEFAULT_BASE_URL).rstrip("/")


def _request_token(api_key: str) -> str:
    """Appel brut au service de jetons ; renvoie le JWT."""
    try:
        response = requests.post(
            f"{base_url()}{TOKEN_PATH}",
            headers={"Accept": "*/*", "Authorization": f"ApiKey {api_key}"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise GarminUnavailable("Garmin est injoignable.") from e
    if response.status_code in (401, 403):
        raise GarminKeyRejected(f"Garmin a refusé la clé (HTTP {response.status_code}).")
    if not response.ok:
        raise GarminUnavailable(f"Garmin a répondu HTTP {response.status_code}.")
    return response.text.strip()


def _jwt_expiration(token: str) -> datetime:
    """Lit la date d'expiration (claim exp) du JWT, sans vérifier sa signature."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(float(claims["exp"]), UTC)
    except (IndexError, KeyError, TypeError, ValueError) as e:
        raise GarminUnavailable("Garmin a renvoyé un jeton illisible.") from e


def exchange_key(api_key: str) -> tuple[str, datetime]:
    """Échange une clé personnelle contre un jeton ; renvoie (jeton, expiration)."""
    token = _request_token(api_key.strip())
    return token, _jwt_expiration(token)


def store_token(account: GarminAccount, token: str, expires_at: datetime) -> None:
    account.token_encrypted = crypto.encrypt(token)
    account.token_expires_at = expires_at


def ensure_token(db: Session, account: GarminAccount, *, force: bool = False) -> str:
    """Jeton valable au moins 1 h, renouvelé si besoin. Met à jour le statut en cas de refus."""
    now = utcnow()
    if (
        not force
        and account.token_encrypted
        and account.token_expires_at
        and account.token_expires_at - now > TOKEN_REFRESH_MARGIN
    ):
        return crypto.decrypt(account.token_encrypted)
    if not account.api_key_encrypted:
        raise GarminKeyRejected("Aucune clé Garmin enregistrée.")
    try:
        token, expires_at = exchange_key(crypto.decrypt(account.api_key_encrypted))
    except GarminKeyRejected as e:
        expired = account.api_key_expires_at is not None and account.api_key_expires_at <= now
        account.status = GarminStatus.key_expired if expired else GarminStatus.error
        account.last_error = str(e)
        db.flush()
        raise
    store_token(account, token, expires_at)
    db.flush()
    return token


_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = _last_request_at + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def call[T](db: Session, account: GarminAccount, fn: Callable[[GarminPersonalApiClient], T]) -> T:
    """Appelle Garmin avec un jeton valide et classe les erreurs.

    - 401 : nouveau jeton une fois ; si Garmin refuse encore, GarminKeyRejected (statut erreur).
    - 429, 5xx, réseau : GarminUnavailable (à réessayer plus tard).
    """
    for attempt in (1, 2):
        client = GarminPersonalApiClient(
            ensure_token(db, account, force=attempt == 2), timeout=TIMEOUT_SECONDS
        )
        _throttle()
        try:
            return fn(client)
        except HttpError as e:
            if e.status_code in (401, 403):
                if attempt == 1:
                    continue
                account.status = GarminStatus.error
                account.last_error = "Garmin refuse l'accès même avec un nouveau jeton."
                db.flush()
                raise GarminKeyRejected(account.last_error) from e
            if e.status_code == 429 or e.status_code >= 500:
                raise GarminUnavailable(f"Garmin a répondu HTTP {e.status_code}.") from e
            raise
        except requests.RequestException as e:
            raise GarminUnavailable("Garmin est injoignable.") from e
        finally:
            client.close()
    raise AssertionError("unreachable")


def key_expires_soon(account: GarminAccount) -> bool:
    if account.api_key_expires_at is None:
        return False
    return account.api_key_expires_at - utcnow() <= KEY_EXPIRY_WARNING
