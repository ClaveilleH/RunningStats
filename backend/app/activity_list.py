"""Liste des activités d'un membre : filtres, tri, pagination, résumé et cumul par semaine."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.accounts import AccessError
from app.config import get_settings
from app.models import Activity, User
from app.security import utcnow

CATEGORIES = ("road", "short_trail", "long_trail", "mixed")
# Nombre de points gardés pour la vignette du tracé (vue cartes).
TRACK_PREVIEW_POINTS = 60


class SortKey(StrEnum):
    date = "date"
    distance = "distance"
    elevation = "elevation"
    duration = "duration"


SORT_COLUMNS = {
    SortKey.date: Activity.start_time,
    SortKey.distance: Activity.distance_m,
    SortKey.elevation: Activity.elevation_gain_m,
    SortKey.duration: Activity.duration_s,
}


@dataclass
class Filters:
    category: str | None = None
    q: str | None = None
    # Dates locales de l'activité, bornes incluses.
    date_from: date | None = None
    date_to: date | None = None


def member_for(db: Session, viewer: User, user_id: int) -> User:
    """Membre dont on lit les activités.

    Les activités d'un ami passeront par le filtre de confidentialité (privacy_settings),
    pas encore construit : en attendant, chacun ne voit que les siennes.
    """
    member = db.get(User, user_id)
    if member is None:
        raise AccessError("Membre introuvable.", 404)
    if member.id != viewer.id:
        raise AccessError(
            "Les activités des amis arriveront avec les réglages de confidentialité.", 403
        )
    return member


def _filtered(user_id: int, filters: Filters) -> Select[Any]:
    stmt = select(Activity).where(Activity.user_id == user_id)
    if filters.category:
        stmt = stmt.where(Activity.category == filters.category)
    if filters.q and filters.q.strip():
        pattern = f"%{filters.q.strip()}%"
        stmt = stmt.where(or_(Activity.name.ilike(pattern), Activity.location_name.ilike(pattern)))
    if filters.date_from:
        stmt = stmt.where(Activity.start_time_local >= datetime.combine(filters.date_from, time()))
    if filters.date_to:
        end = datetime.combine(filters.date_to + timedelta(days=1), time())
        stmt = stmt.where(Activity.start_time_local < end)
    return stmt


def summary(db: Session, user_id: int, filters: Filters) -> dict[str, float | int]:
    sub = _filtered(user_id, filters).subquery()
    row = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(sub.c.distance_m), 0),
            func.coalesce(func.sum(sub.c.elevation_gain_m), 0),
            func.coalesce(func.sum(sub.c.duration_s), 0),
        ).select_from(sub)
    ).one()
    return {
        "count": row[0],
        "distance_m": float(row[1]),
        "elevation_gain_m": float(row[2]),
        "duration_s": float(row[3]),
    }


def page(
    db: Session,
    user_id: int,
    filters: Filters,
    sort: SortKey,
    descending: bool,
    page_number: int,
    page_size: int,
) -> list[Activity]:
    column = SORT_COLUMNS[sort]
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    stmt = (
        _filtered(user_id, filters)
        .order_by(order, Activity.id.desc())
        .offset((page_number - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(stmt))


def track_previews(db: Session, activity_ids: list[int]) -> dict[int, list[list[float]]]:
    """Tracé simplifié : environ 60 points [lat, lon] pris à intervalle régulier."""
    if not activity_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT activity_id, lat, lon FROM (
                SELECT activity_id, seq, lat, lon,
                       row_number() OVER (PARTITION BY activity_id ORDER BY seq) - 1 AS rn,
                       count(*) OVER (PARTITION BY activity_id) AS n
                FROM activity_points
                WHERE activity_id = ANY(:ids) AND lat IS NOT NULL AND lon IS NOT NULL
            ) p
            WHERE rn % GREATEST(n / :points, 1) = 0 OR rn = n - 1
            ORDER BY activity_id, seq
            """
        ),
        {"ids": activity_ids, "points": TRACK_PREVIEW_POINTS},
    )
    previews: dict[int, list[list[float]]] = {}
    for activity_id, lat, lon in rows:
        previews.setdefault(activity_id, []).append([round(lat, 5), round(lon, 5)])
    return previews


def _today() -> date:
    return utcnow().astimezone(ZoneInfo(get_settings().timezone)).date()


def weekly(
    db: Session, user_id: int, weeks: int, today: date | None = None
) -> list[dict[str, Any]]:
    """Km, D+ et nombre de sorties par semaine (lundi → dimanche), semaine en cours comprise."""
    today = today or _today()
    current_monday = today - timedelta(days=today.weekday())
    first_monday = current_monday - timedelta(weeks=weeks - 1)
    week = func.date_trunc("week", Activity.start_time_local)
    rows = db.execute(
        select(
            week,
            func.count(),
            func.coalesce(func.sum(Activity.distance_m), 0),
            func.coalesce(func.sum(Activity.elevation_gain_m), 0),
        )
        .where(
            and_(
                Activity.user_id == user_id,
                Activity.start_time_local >= datetime.combine(first_monday, time()),
            )
        )
        .group_by(week)
    ).all()
    by_week = {r[0].date(): r for r in rows}
    result = []
    for i in range(weeks):
        monday = first_monday + timedelta(weeks=i)
        row = by_week.get(monday)
        result.append(
            {
                "week_start": monday,
                "count": row[1] if row else 0,
                "distance_m": float(row[2]) if row else 0.0,
                "elevation_gain_m": float(row[3]) if row else 0.0,
                "current": monday == current_monday,
            }
        )
    return result
