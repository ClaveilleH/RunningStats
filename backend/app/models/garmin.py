import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class GarminSource(enum.StrEnum):
    personal_api = "personal_api"  # API personnelle officielle de Garmin (par défaut)
    garminconnect = "garminconnect"  # repli : bibliothèque non officielle
    fit_import = "fit_import"  # repli : import manuel de fichiers FIT


class GarminStatus(enum.StrEnum):
    ok = "ok"
    key_expired = "key_expired"
    error = "error"


class GarminAccount(Base):
    """Connexion Garmin d'un membre (une seule par membre)."""

    __tablename__ = "garmin_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    source: Mapped[GarminSource] = mapped_column(
        Enum(GarminSource, name="garmin_source", values_callable=_values),
        default=GarminSource.personal_api,
    )
    # Secrets chiffrés avec app.crypto ; jamais en clair en base ni dans les logs.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    # Date de fin de validité de la clé, saisie par le membre (Garmin ne la renvoie pas).
    api_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[GarminStatus] = mapped_column(
        Enum(GarminStatus, name="garmin_status", values_callable=_values),
        default=GarminStatus.ok,
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Où reprendre la synchro (ex. date de la dernière activité vue).
    sync_cursor: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
