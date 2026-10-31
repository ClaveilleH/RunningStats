"""Fiche d'une activité : résumé, splits, zones FC, points allégés pour la carte et les courbes."""

from bisect import bisect_left, bisect_right
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import AccessError
from app.models import Activity, ActivityLap, ActivityPoint, LapKind, User

# Fenêtre (m) de part et d'autre d'un point pour lisser l'allure des courbes.
PACE_WINDOW_M = 100
# Au-delà, l'allure n'a pas de sens (marche lente, arrêt) : point laissé vide.
MAX_PACE_S_PER_KM = 30 * 60


def activity_for(db: Session, viewer: User, activity_id: int) -> Activity:
    """Activité lisible par le membre.

    Comme pour la liste, les sorties des amis attendent le filtre de confidentialité.
    """
    activity = db.get(Activity, activity_id)
    if activity is None or activity.user_id != viewer.id:
        # 404 aussi pour un ami : on ne révèle pas qu'une activité existe.
        raise AccessError("Activité introuvable.", 404)
    return activity


def laps(db: Session, activity: Activity, kind: LapKind) -> list[ActivityLap]:
    return list(
        db.scalars(
            select(ActivityLap)
            .where(ActivityLap.activity_id == activity.id, ActivityLap.kind == kind)
            .order_by(ActivityLap.index)
        )
    )


def _number(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    return float(value) if isinstance(value, int | float) else None


def details(activity: Activity) -> dict[str, float | None]:
    """Valeurs complémentaires du résumé Garmin."""
    raw = activity.raw_summary or {}
    elapsed = _number(raw, "elapsedDuration")
    stopped = None
    if elapsed is not None and activity.duration_s is not None:
        stopped = max(0.0, elapsed - activity.duration_s)
    return {
        "elapsed_s": elapsed,
        "stopped_s": stopped,
        "avg_cadence_spm": _number(raw, "averageRunningCadenceInStepsPerMinute"),
        "calories": _number(raw, "calories"),
        "min_altitude_m": _number(raw, "minElevation"),
        "max_altitude_m": _number(raw, "maxElevation"),
    }


def points(db: Session, activity: Activity, step_m: float) -> dict[str, list[Any]]:
    """Un point tous les step_m mètres, en colonnes (plus léger en JSON).

    L'allure est le temps chrono sur ±100 m autour du point : les pauses n'y comptent pas.
    """
    rows = db.execute(
        select(
            ActivityPoint.distance_m,
            ActivityPoint.timer_s,
            ActivityPoint.lat,
            ActivityPoint.lon,
            ActivityPoint.altitude_m,
            ActivityPoint.hr,
            ActivityPoint.cadence_spm,
        )
        .where(
            ActivityPoint.activity_id == activity.id,
            ActivityPoint.distance_m.is_not(None),
            ActivityPoint.timer_s.is_not(None),
        )
        .order_by(ActivityPoint.seq)
    ).all()
    columns: dict[str, list[Any]] = {
        key: []
        for key in ("distance_m", "timer_s", "lat", "lon", "altitude_m", "hr", "cadence_spm")
    }
    columns["pace_s_per_km"] = []
    if not rows:
        return columns

    distances = [r[0] for r in rows]
    timers = [r[1] for r in rows]
    next_at = 0.0
    for i, row in enumerate(rows):
        distance = row[0]
        if distance < next_at and i != len(rows) - 1:
            continue
        next_at = distance + step_m
        lo = bisect_left(distances, distance - PACE_WINDOW_M)
        hi = min(bisect_right(distances, distance + PACE_WINDOW_M), len(rows)) - 1
        span = distances[hi] - distances[lo]
        pace = (timers[hi] - timers[lo]) / span * 1000 if span > 20 else None
        for key, value in zip(columns, row, strict=False):
            columns[key].append(value)
        columns["pace_s_per_km"].append(
            round(pace, 1) if pace is not None and pace <= MAX_PACE_S_PER_KM else None
        )
    for key in ("distance_m", "timer_s", "altitude_m"):
        columns[key] = [round(v, 1) if v is not None else None for v in columns[key]]
    for key in ("lat", "lon"):
        columns[key] = [round(v, 6) if v is not None else None for v in columns[key]]
    return columns
