from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app import activity_detail, activity_list, readiness
from app.activity_list import Filters, SortKey
from app.api.deps import CurrentUser, DbSession
from app.models import Activity, LapKind
from app.schemas import (
    ActivityDetailsOut,
    ActivityItemOut,
    ActivityListOut,
    ActivityOut,
    ActivityPointsOut,
    ActivitySummaryOut,
    ReadinessOut,
    SplitOut,
    WeekOut,
)

router = APIRouter(prefix="/users/{user_id}/activities", tags=["activities"])
activity_router = APIRouter(prefix="/activities", tags=["activities"])

Category = Literal["road", "short_trail", "long_trail", "mixed"]


def _item(activity: Activity, track: list[list[float]] | None) -> ActivityItemOut:
    pace = None
    if activity.distance_m and activity.duration_s and activity.distance_m > 0:
        pace = activity.duration_s / (activity.distance_m / 1000)
    return ActivityItemOut(
        id=activity.id,
        name=activity.name,
        activity_type=activity.activity_type,
        category=activity.category,
        start_time=activity.start_time,
        start_time_local=activity.start_time_local,
        location_name=activity.location_name,
        distance_m=activity.distance_m,
        duration_s=activity.duration_s,
        elevation_gain_m=activity.elevation_gain_m,
        avg_hr=activity.avg_hr,
        pace_s_per_km=pace,
        pinned=activity.pinned,
        track=track,
    )


@router.get("", response_model=ActivityListOut)
def list_activities(
    user_id: int,
    viewer: CurrentUser,
    db: DbSession,
    category: Category | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    sort: SortKey = SortKey.date,
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    with_track: bool = False,
) -> ActivityListOut:
    """Liste filtrable et triable, avec les totaux de la sélection."""
    member = activity_list.member_for(db, viewer, user_id)
    filters = Filters(category=category, q=q, date_from=date_from, date_to=date_to)
    totals = activity_list.summary(db, member.id, filters)
    activities = activity_list.page(db, member.id, filters, sort, order == "desc", page, page_size)
    tracks = activity_list.track_previews(db, [a.id for a in activities]) if with_track else {}
    return ActivityListOut(
        items=[_item(a, tracks.get(a.id) if with_track else None) for a in activities],
        total=int(totals["count"]),
        page=page,
        page_size=page_size,
        summary=ActivitySummaryOut.model_validate(totals),
    )


@router.get("/weekly", response_model=list[WeekOut])
def weekly_activities(
    user_id: int,
    viewer: CurrentUser,
    db: DbSession,
    weeks: Annotated[int, Query(ge=1, le=104)] = 12,
) -> list[WeekOut]:
    """Km et D+ par semaine pour le graphique, semaine en cours en dernier."""
    member = activity_list.member_for(db, viewer, user_id)
    return [WeekOut.model_validate(w) for w in activity_list.weekly(db, member.id, weeks)]


@activity_router.get("/{activity_id}", response_model=ActivityOut)
def get_activity(activity_id: int, viewer: CurrentUser, db: DbSession) -> ActivityOut:
    """Résumé, splits par km, tours de la montre, zones FC et détails."""
    activity = activity_detail.activity_for(db, viewer, activity_id)
    item = _item(activity, None)
    return ActivityOut(
        **item.model_dump(),
        user_id=activity.user_id,
        moving_duration_s=activity.moving_duration_s,
        elevation_loss_m=activity.elevation_loss_m,
        max_hr=activity.max_hr,
        km_effort=activity.km_effort,
        hr_zones_s=activity.hr_zones_s,
        details=ActivityDetailsOut.model_validate(activity_detail.details(activity)),
        km_splits=[
            SplitOut.model_validate(lap) for lap in activity_detail.laps(db, activity, LapKind.km)
        ],
        laps=[
            SplitOut.model_validate(lap) for lap in activity_detail.laps(db, activity, LapKind.lap)
        ],
        processed=activity.processed_at is not None,
    )


@activity_router.get("/{activity_id}/points", response_model=ActivityPointsOut)
def get_activity_points(
    activity_id: int,
    viewer: CurrentUser,
    db: DbSession,
    step: Annotated[float, Query(ge=5, le=1000)] = 25,
) -> ActivityPointsOut:
    """Points pour la carte, le profil et les courbes : un tous les `step` mètres."""
    activity = activity_detail.activity_for(db, viewer, activity_id)
    return ActivityPointsOut(step_m=step, **activity_detail.points(db, activity, step))


@activity_router.get("/{activity_id}/readiness", response_model=ReadinessOut)
def get_readiness(activity_id: int, viewer: CurrentUser, db: DbSession) -> ReadinessOut:
    """Forme avant la sortie : sommeil des 3 nuits pondéré, FC au repos, Body Battery."""
    activity = activity_detail.activity_for(db, viewer, activity_id)
    return ReadinessOut.model_validate(readiness.compute(db, activity))


@activity_router.put("/{activity_id}/pin", response_model=ActivityItemOut)
def pin_activity(activity_id: int, viewer: CurrentUser, db: DbSession) -> ActivityItemOut:
    """Épingle la sortie sur le profil."""
    activity = activity_detail.activity_for(db, viewer, activity_id)
    activity.pinned = True
    db.commit()
    return _item(activity, None)


@activity_router.delete("/{activity_id}/pin", response_model=ActivityItemOut)
def unpin_activity(activity_id: int, viewer: CurrentUser, db: DbSession) -> ActivityItemOut:
    activity = activity_detail.activity_for(db, viewer, activity_id)
    activity.pinned = False
    db.commit()
    return _item(activity, None)
