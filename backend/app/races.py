"""Courses à venir : liste partagée, « J'y vais », lien avec la sortie du jour J."""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import metrics, settings
from app.accounts import AccessError
from app.config import get_settings
from app.models import Activity, Race, RaceParticipant, Role, User
from app.security import utcnow
from app.settings import ActivityCategories, RaceLinking

RACE_METRICS_VERSION = 1


def today() -> date:
    return utcnow().astimezone(ZoneInfo(get_settings().timezone)).date()


def get_race(db: Session, race_id: int) -> Race:
    race = db.get(Race, race_id)
    if race is None:
        raise AccessError("Course introuvable.", 404)
    return race


def check_can_edit(race: Race, user: User) -> None:
    """Modifier ou supprimer : l'auteur de la course ou l'admin."""
    if race.created_by != user.id and user.role != Role.admin:
        raise AccessError("Seul l'auteur de la course ou l'admin peut la modifier.", 403)


def compute_metrics(db: Session, race: Race) -> None:
    """Catégorie et km-effort, avec les mêmes seuils que les activités."""
    rules = settings.get(db, ActivityCategories)
    # Une course n'a pas de type Garmin : seul le D+ par km décide.
    category, trace = metrics.classify("running", race.distance_m, race.elevation_gain_m, rules)
    race.category = category
    race.km_effort = round(metrics.km_effort(race.distance_m, race.elevation_gain_m), 2)
    race.calc_trace = {"category": trace, "version": RACE_METRICS_VERSION}


def participants(db: Session, race_ids: list[int]) -> dict[int, list[tuple[RaceParticipant, User]]]:
    rows = db.execute(
        select(RaceParticipant, User)
        .join(User, User.id == RaceParticipant.user_id)
        .where(RaceParticipant.race_id.in_(race_ids))
        .order_by(RaceParticipant.joined_at)
    ).all()
    by_race: dict[int, list[tuple[RaceParticipant, User]]] = {}
    for participant, user in rows:
        by_race.setdefault(participant.race_id, []).append((participant, user))
    return by_race


def list_races(
    db: Session,
    *,
    past: bool,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
) -> list[Race]:
    """À venir (aujourd'hui compris) de la plus proche à la plus lointaine, ou passées
    de la plus récente à la plus ancienne."""
    day = today()
    stmt = select(Race)
    stmt = stmt.where(Race.date < day) if past else stmt.where(Race.date >= day)
    if date_from:
        stmt = stmt.where(Race.date >= date_from)
    if date_to:
        stmt = stmt.where(Race.date <= date_to)
    if category:
        stmt = stmt.where(Race.category == category)
    order = (Race.date.desc(), Race.id.desc()) if past else (Race.date, Race.id)
    return list(db.scalars(stmt.order_by(*order)))


def join(db: Session, race: Race, user: User) -> RaceParticipant:
    participant = db.get(RaceParticipant, (race.id, user.id))
    if participant is None:
        participant = RaceParticipant(race_id=race.id, user_id=user.id)
        db.add(participant)
        db.flush()
    # Inscription après coup (course déjà courue) : on relie tout de suite la sortie.
    if race.date <= today():
        link_participant(db, race, participant)
    return participant


def leave(db: Session, race: Race, user: User) -> None:
    participant = db.get(RaceParticipant, (race.id, user.id))
    if participant is not None:
        db.delete(participant)


def _matching_activity(db: Session, race: Race, user_id: int) -> Activity | None:
    """Sortie du membre le jour de la course, à ± 15 % de sa distance (la plus proche)."""
    tolerance = settings.get(db, RaceLinking).distance_tolerance_pct / 100
    start = datetime.combine(race.date, time())
    candidates = db.scalars(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.start_time_local >= start,
            Activity.start_time_local < start + timedelta(days=1),
            Activity.distance_m.is_not(None),
        )
    ).all()
    matching = [
        a
        for a in candidates
        if abs((a.distance_m or 0) - race.distance_m) <= tolerance * race.distance_m
    ]
    return min(matching, key=lambda a: abs((a.distance_m or 0) - race.distance_m), default=None)


def link_participant(db: Session, race: Race, participant: RaceParticipant) -> None:
    activity = _matching_activity(db, race, participant.user_id)
    if activity is not None:
        # Une sortie ne compte que pour une course (cas rare de deux courses le même jour).
        taken = db.scalar(
            select(RaceParticipant).where(
                RaceParticipant.activity_id == activity.id,
                RaceParticipant.race_id != race.id,
            )
        )
        if taken is not None:
            return
    participant.activity_id = activity.id if activity else None


def relink_race(db: Session, race: Race) -> None:
    """Après une modification (date, distance) : on refait le lien de chaque inscrit."""
    for participant in db.scalars(
        select(RaceParticipant).where(RaceParticipant.race_id == race.id)
    ):
        if race.date <= today():
            link_participant(db, race, participant)
        else:
            participant.activity_id = None


def link_activity(db: Session, activity: Activity) -> Race | None:
    """Pipeline d'une nouvelle activité : la relier à une course du membre ce jour-là."""
    day = activity.start_time_local.date()
    rows = db.execute(
        select(Race, RaceParticipant)
        .join(RaceParticipant, RaceParticipant.race_id == Race.id)
        .where(RaceParticipant.user_id == activity.user_id, Race.date == day)
    ).all()
    for race, participant in rows:
        if participant.activity_id is not None:
            continue
        if _matching_activity(db, race, activity.user_id) is activity:
            participant.activity_id = activity.id
            return race
    return None


def is_race_day(db: Session, user_id: int, day: date) -> bool:
    return (
        db.scalar(
            select(RaceParticipant.race_id)
            .join(Race, Race.id == RaceParticipant.race_id)
            .where(RaceParticipant.user_id == user_id, Race.date == day)
            .limit(1)
        )
        is not None
    )


def races_of_activities(db: Session, activity_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Course reliée à chaque activité, pour le badge « Course »."""
    if not activity_ids:
        return {}
    rows = db.execute(
        select(RaceParticipant.activity_id, Race.id, Race.name)
        .join(Race, Race.id == RaceParticipant.race_id)
        .where(RaceParticipant.activity_id.in_(activity_ids))
    ).all()
    return {activity_id: {"id": race_id, "name": name} for activity_id, race_id, name in rows}
