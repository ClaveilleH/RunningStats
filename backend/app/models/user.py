import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(enum.StrEnum):
    admin = "admin"
    member = "member"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    # Pseudo : choisi plus tard dans Réglages, donc facultatif à la création.
    username: Mapped[str | None] = mapped_column(String(40), unique=True)
    # Toujours stocké en minuscules (voir app.security.normalize_email).
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_color: Mapped[str | None] = mapped_column(String(7))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=Role.member,
    )
    theme: Mapped[str] = mapped_column(String(10), default="system")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_analyze_big_races: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fréquence de synchro propre au membre ; vide = celle du groupe.
    sync_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
