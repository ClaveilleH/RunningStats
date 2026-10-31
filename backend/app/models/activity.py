import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Périmètre du site (décision du 31/10/2026 : trail_running inclus, tapis exclu).
RUNNING_TYPES = frozenset({"running", "trail_running", "track_running"})


class Activity(Base):
    """Une sortie course ou trail, créée depuis le résumé Garmin puis complétée par le FIT."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_user_start", "user_id", "start_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    garmin_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    activity_type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(String(200))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # UTC
    # Heure locale de la montre, sans fuseau (le fuseau n'est pas dans le résumé Garmin).
    start_time_local: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    distance_m: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    moving_duration_s: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    elevation_loss_m: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[int | None] = mapped_column(SmallInteger)
    max_hr: Mapped[int | None] = mapped_column(SmallInteger)
    # Secondes passées dans les zones FC 1 à 5, selon Garmin.
    hr_zones_s: Mapped[list[float] | None] = mapped_column(JSONB)
    location_name: Mapped[str | None] = mapped_column(String(200))
    # Calculés à l'étape suivante (catégorie route / trail, km-effort) ; vides pour l'instant.
    category: Mapped[str | None] = mapped_column(String(20))
    km_effort: Mapped[float | None] = mapped_column(Float)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    # Chemin du FIT brut, relatif à DATA_DIR.
    fit_path: Mapped[str | None] = mapped_column(String(300))
    raw_summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Rempli quand le FIT a été téléchargé et lu (points et tours en base).
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityPoint(Base):
    """Un point du FIT (environ 1 par seconde)."""

    __tablename__ = "activity_points"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Secondes depuis le premier point.
    t_s: Mapped[float] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    speed_ms: Mapped[float | None] = mapped_column(Float)
    hr: Mapped[int | None] = mapped_column(SmallInteger)
    # Pas par minute (les deux pieds).
    cadence_spm: Mapped[int | None] = mapped_column(SmallInteger)


class LapKind(enum.StrEnum):
    lap = "lap"  # tours enregistrés par la montre
    km = "km"  # splits par km, calculés depuis les points (étape suivante)


class ActivityLap(Base):
    __tablename__ = "activity_laps"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[LapKind] = mapped_column(
        Enum(LapKind, name="lap_kind", values_callable=lambda e: [m.value for m in e])
    )
    index: Mapped[int] = mapped_column(Integer)
    start_distance_m: Mapped[float | None] = mapped_column(Float)
    end_distance_m: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    elevation_loss_m: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[int | None] = mapped_column(SmallInteger)
