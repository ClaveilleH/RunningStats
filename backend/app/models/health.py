from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SleepNight(Base):
    """Une nuit de sommeil ; date = jour du réveil (calendarDate de Garmin)."""

    __tablename__ = "sleep_nights"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_s: Mapped[int | None] = mapped_column(Integer)
    deep_s: Mapped[int | None] = mapped_column(Integer)
    light_s: Mapped[int | None] = mapped_column(Integer)
    rem_s: Mapped[int | None] = mapped_column(Integer)
    awake_s: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    avg_hr: Mapped[int | None] = mapped_column(SmallInteger)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Weight(Base):
    """Une pesée (plusieurs possibles par jour)."""

    __tablename__ = "weights"
    __table_args__ = (UniqueConstraint("user_id", "garmin_sample_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    garmin_sample_id: Mapped[int] = mapped_column(BigInteger)
    date: Mapped[date] = mapped_column(Date)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weight_kg: Mapped[float] = mapped_column(Float)


class DailyHealth(Base):
    """Valeurs santé d'une journée."""

    __tablename__ = "daily_health"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    steps: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[int | None] = mapped_column(SmallInteger)
    body_battery_min: Mapped[int | None] = mapped_column(SmallInteger)
    body_battery_max: Mapped[int | None] = mapped_column(SmallInteger)
    # VFC moyenne de la nuit (ms) ; vide si la montre ne la fournit pas.
    hrv_ms: Mapped[float | None] = mapped_column(Float)
