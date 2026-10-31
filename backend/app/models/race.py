from datetime import date, datetime, time
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Race(Base):
    """Une course enregistrée sur le site, partagée par le groupe."""

    __tablename__ = "races"
    __table_args__ = (Index("ix_races_date", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # Date et heure de départ locales (fuseau du lieu de la course).
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    location: Mapped[str | None] = mapped_column(String(120))
    distance_m: Mapped[float] = mapped_column(Float)
    elevation_gain_m: Mapped[float] = mapped_column(Float, default=0)
    # Calculés comme pour une activité : road / short_trail / long_trail / mixed, km + D+/100.
    category: Mapped[str] = mapped_column(String(20))
    km_effort: Mapped[float] = mapped_column(Float)
    calc_trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    official_url: Mapped[str | None] = mapped_column(String(500))
    # GPX officiel, relatif à DATA_DIR (ajouté avec la fiche de course).
    gpx_path: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RaceParticipant(Base):
    """« J'y vais » : un membre inscrit à une course."""

    __tablename__ = "race_participants"

    race_id: Mapped[int] = mapped_column(
        ForeignKey("races.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Sortie du jour J, reliée automatiquement après la course.
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), unique=True
    )
