from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app import activity_list
from app.activity_list import Filters, SortKey
from app.api.deps import CurrentUser, DbSession
from app.models import Activity
from app.schemas import ActivityItemOut, ActivityListOut, ActivitySummaryOut, WeekOut

router = APIRouter(prefix="/users/{user_id}/activities", tags=["activities"])

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
