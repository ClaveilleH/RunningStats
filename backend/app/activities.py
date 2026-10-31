"""Création des activités depuis Garmin et stockage de leurs données brutes."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app import fit
from app.config import get_settings
from app.models import Activity, ActivityLap, ActivityPoint, LapKind
from app.models.activity import RUNNING_TYPES
from app.security import utcnow

GARMIN_DATETIME = "%Y-%m-%d %H:%M:%S"


def is_running(summary: dict[str, Any]) -> bool:
    return (summary.get("activityType") or {}).get("typeKey") in RUNNING_TYPES


def _garmin_datetime(value: str) -> datetime:
    return datetime.strptime(value, GARMIN_DATETIME)


def activity_from_summary(user_id: int, summary: dict[str, Any]) -> Activity:
    """Résumé de la liste des activités Garmin → Activity (sans les points du FIT)."""
    zones = [summary.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
    return Activity(
        user_id=user_id,
        garmin_id=int(summary["activityId"]),
        activity_type=summary["activityType"]["typeKey"],
        name=summary.get("activityName"),
        start_time=_garmin_datetime(summary["startTimeGMT"]).replace(tzinfo=UTC),
        start_time_local=_garmin_datetime(summary["startTimeLocal"]),
        distance_m=summary.get("distance"),
        duration_s=summary.get("duration"),
        moving_duration_s=summary.get("movingDuration"),
        elevation_gain_m=summary.get("elevationGain"),
        elevation_loss_m=summary.get("elevationLoss"),
        avg_hr=_int(summary.get("averageHR")),
        max_hr=_int(summary.get("maxHR")),
        hr_zones_s=zones if any(z is not None for z in zones) else None,
        location_name=summary.get("locationName"),
        raw_summary=summary,
    )


def _int(value: Any) -> int | None:
    return round(value) if isinstance(value, int | float) else None


def fit_relative_path(activity: Activity) -> Path:
    return Path("fit") / str(activity.user_id) / f"{activity.garmin_id}.zip"


def save_raw_fit(activity: Activity, content: bytes) -> None:
    """Garde le fichier tel que Garmin l'a envoyé, dans DATA_DIR/fit/<membre>/."""
    relative = fit_relative_path(activity)
    path = get_settings().data_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(content)
    tmp.replace(path)
    activity.fit_path = relative.as_posix()


def store_fit_data(db: Session, activity: Activity, parsed: fit.ParsedFit) -> None:
    """Remplace les points et les tours de la montre par ceux du FIT."""
    db.execute(delete(ActivityPoint).where(ActivityPoint.activity_id == activity.id))
    db.execute(
        delete(ActivityLap).where(
            ActivityLap.activity_id == activity.id, ActivityLap.kind == LapKind.lap
        )
    )
    if parsed.points:
        db.execute(
            insert(ActivityPoint), [{"activity_id": activity.id, **p} for p in parsed.points]
        )
    if parsed.laps:
        db.execute(
            insert(ActivityLap),
            [{"activity_id": activity.id, "kind": LapKind.lap, **lap} for lap in parsed.laps],
        )
    activity.processed_at = utcnow()
