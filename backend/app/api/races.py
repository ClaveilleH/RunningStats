from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app import races
from app.api.deps import CurrentUser, DbSession
from app.models import Race, RaceParticipant, Role, User
from app.schemas import RaceIn, RaceOut, RaceParticipantOut

router = APIRouter(prefix="/races", tags=["races"])

Category = Literal["road", "short_trail", "long_trail", "mixed"]


def _out(
    race: Race,
    people: list[tuple[RaceParticipant, User]],
    viewer: User,
    authors: dict[int, str],
) -> RaceOut:
    return RaceOut(
        id=race.id,
        name=race.name,
        date=race.date,
        start_time=race.start_time,
        location=race.location,
        distance_m=race.distance_m,
        elevation_gain_m=race.elevation_gain_m,
        category=race.category,
        km_effort=race.km_effort,
        official_url=race.official_url,
        created_by=race.created_by,
        created_by_name=authors.get(race.created_by) if race.created_by else None,
        can_edit=race.created_by == viewer.id or viewer.role == Role.admin,
        joined=any(p.user_id == viewer.id for p, _ in people),
        participants=[
            RaceParticipantOut(
                user_id=user.id,
                display_name=user.display_name,
                avatar_color=user.avatar_color,
                joined_at=p.joined_at,
                activity_id=p.activity_id if user.id == viewer.id else None,
            )
            for p, user in people
        ],
    )


def _outs(db: DbSession, race_list: list[Race], viewer: User) -> list[RaceOut]:
    people = races.participants(db, [r.id for r in race_list])
    author_ids = {r.created_by for r in race_list if r.created_by}
    authors = {u.id: u.display_name for u in db.query(User).filter(User.id.in_(author_ids))}
    return [_out(r, people.get(r.id, []), viewer, authors) for r in race_list]


def _apply(race: Race, body: RaceIn) -> None:
    race.name = body.name.strip()
    race.date = body.date
    race.start_time = body.start_time
    race.location = body.location.strip() if body.location and body.location.strip() else None
    race.distance_m = body.distance_m
    race.elevation_gain_m = body.elevation_gain_m
    race.official_url = str(body.official_url) if body.official_url else None


@router.get("", response_model=list[RaceOut])
def list_races(
    viewer: CurrentUser,
    db: DbSession,
    past: bool = False,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    category: Category | None = None,
) -> list[RaceOut]:
    """Liste partagée du groupe : à venir par défaut, passées avec past=true."""
    found = races.list_races(db, past=past, date_from=date_from, date_to=date_to, category=category)
    return _outs(db, found, viewer)


@router.post("", response_model=RaceOut, status_code=status.HTTP_201_CREATED)
def create_race(body: RaceIn, viewer: CurrentUser, db: DbSession) -> RaceOut:
    """Ajoute une course. Le GPX et les ravitos viendront avec la fiche de course."""
    race = Race(created_by=viewer.id)
    _apply(race, body)
    races.compute_metrics(db, race)
    db.add(race)
    db.commit()
    return _outs(db, [race], viewer)[0]


@router.get("/{race_id}", response_model=RaceOut)
def get_race(race_id: int, viewer: CurrentUser, db: DbSession) -> RaceOut:
    return _outs(db, [races.get_race(db, race_id)], viewer)[0]


@router.put("/{race_id}", response_model=RaceOut)
def update_race(race_id: int, body: RaceIn, viewer: CurrentUser, db: DbSession) -> RaceOut:
    race = races.get_race(db, race_id)
    races.check_can_edit(race, viewer)
    _apply(race, body)
    races.compute_metrics(db, race)
    races.relink_race(db, race)
    db.commit()
    return _outs(db, [race], viewer)[0]


@router.delete("/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_race(race_id: int, viewer: CurrentUser, db: DbSession) -> None:
    race = races.get_race(db, race_id)
    races.check_can_edit(race, viewer)
    db.delete(race)
    db.commit()


@router.post("/{race_id}/participation", response_model=RaceOut)
def join_race(race_id: int, viewer: CurrentUser, db: DbSession) -> RaceOut:
    """« J'y vais »."""
    race = races.get_race(db, race_id)
    races.join(db, race, viewer)
    db.commit()
    return _outs(db, [race], viewer)[0]


@router.delete("/{race_id}/participation", response_model=RaceOut)
def leave_race(race_id: int, viewer: CurrentUser, db: DbSession) -> RaceOut:
    """Ne plus y aller."""
    race = races.get_race(db, race_id)
    races.leave(db, race, viewer)
    db.commit()
    return _outs(db, [race], viewer)[0]
