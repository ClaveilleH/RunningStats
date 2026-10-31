"""Calculs sur une activité : catégorie, km-effort, splits par km.

Chaque calcul renvoie sa trace (méthode, version, paramètres, entrées) : elle est gardée
dans Activity.calc_trace pour le futur bouton « Explication ».
"""

from dataclasses import dataclass
from statistics import fmean
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app import settings
from app.models import Activity, ActivityLap, ActivityPoint, LapKind
from app.settings import ActivityCategories

METRICS_VERSION = 2  # v2 : durées des splits sans les pauses
SPLIT_LENGTH_M = 1000.0
# Seuil d'hystérésis sur l'altitude pour répartir le D+ entre les splits (calé sur les
# vraies sorties : écart médian de +2,6 % avec le D+ Garmin à 1 m).
ALTITUDE_HYSTERESIS_M = 1.0


class Category:
    road = "road"
    short_trail = "short_trail"
    long_trail = "long_trail"
    mixed = "mixed"


def km_effort(distance_m: float, elevation_gain_m: float) -> float:
    """Taille d'effort : km + D+ / 100."""
    return distance_m / 1000 + elevation_gain_m / 100


def classify(
    activity_type: str, distance_m: float, elevation_gain_m: float, rules: ActivityCategories
) -> tuple[str, dict[str, Any]]:
    """Catégorie selon le type Garmin et le D+ par km.

    - piste : route ;
    - D+/km au-dessus du seuil trail : trail (court ou long selon le km-effort) ;
    - D+/km sous le seuil route : route, sauf une sortie marquée trail sur la montre (mixte) ;
    - entre les deux : mixte, sauf une sortie marquée trail (trail).
    """
    dplus_per_km = elevation_gain_m / (distance_m / 1000) if distance_m > 0 else 0.0
    effort = km_effort(distance_m, elevation_gain_m)
    is_trail_type = activity_type == "trail_running"

    if activity_type == "track_running":
        category = Category.road
    elif dplus_per_km >= rules.trail_min_dplus_per_km or (
        is_trail_type and dplus_per_km >= rules.road_max_dplus_per_km
    ):
        category = (
            Category.long_trail
            if effort >= rules.long_trail_min_km_effort
            else Category.short_trail
        )
    elif dplus_per_km < rules.road_max_dplus_per_km and not is_trail_type:
        category = Category.road
    else:
        category = Category.mixed

    trace = {
        "method": "type_and_dplus_per_km",
        "params": rules.model_dump(exclude={"key"}),
        "inputs": {
            "activity_type": activity_type,
            "distance_m": distance_m,
            "elevation_gain_m": elevation_gain_m,
            "dplus_per_km": round(dplus_per_km, 2),
            "km_effort": round(effort, 2),
        },
    }
    return category, trace


@dataclass
class _Point:
    t_s: float
    distance_m: float
    altitude_m: float | None
    hr: int | None


def _elevation_changes(points: list[_Point]) -> tuple[list[float], list[float]]:
    """Montée et descente attribuées à chaque point, avec un seuil d'hystérésis."""
    gains = [0.0] * len(points)
    losses = [0.0] * len(points)
    ref: float | None = None
    for i, p in enumerate(points):
        if p.altitude_m is None:
            continue
        if ref is None:
            ref = p.altitude_m
        elif p.altitude_m - ref >= ALTITUDE_HYSTERESIS_M:
            gains[i] = p.altitude_m - ref
            ref = p.altitude_m
        elif ref - p.altitude_m >= ALTITUDE_HYSTERESIS_M:
            losses[i] = ref - p.altitude_m
            ref = p.altitude_m
    return gains, losses


def _time_at(points: list[_Point], i: int, distance: float) -> float:
    """Temps interpolé au passage d'une distance, entre les points i-1 et i."""
    a, b = points[i - 1], points[i]
    if b.distance_m == a.distance_m:
        return b.t_s
    ratio = (distance - a.distance_m) / (b.distance_m - a.distance_m)
    return a.t_s + ratio * (b.t_s - a.t_s)


def km_splits(
    raw_points: list[ActivityPoint],
    total_gain_m: float | None,
    total_loss_m: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Splits de 1 km (le dernier peut être plus court).

    Le D+ / D- de chaque split suit le profil d'altitude du FIT, puis est mis à l'échelle
    pour que la somme des splits égale le D+ / D- officiel de Garmin.
    """
    points = [
        # Temps chrono (sans les pauses) ; temps écoulé pour les anciens points sans chrono.
        _Point(p.timer_s if p.timer_s is not None else p.t_s, p.distance_m, p.altitude_m, p.hr)
        for p in raw_points
        if p.distance_m is not None
    ]
    trace: dict[str, Any] = {
        "method": "interpolated_km_splits",
        "params": {
            "split_length_m": SPLIT_LENGTH_M,
            "time": "timer_excluding_pauses",
            "altitude_hysteresis_m": ALTITUDE_HYSTERESIS_M,
            "elevation_scaled_to_garmin_total": True,
        },
    }
    if len(points) < 2:
        return [], {**trace, "inputs": {"points": len(points)}}

    gains, losses = _elevation_changes(points)
    raw_gain, raw_loss = sum(gains), sum(losses)
    gain_scale = total_gain_m / raw_gain if total_gain_m is not None and raw_gain > 0 else 1.0
    loss_scale = total_loss_m / raw_loss if total_loss_m is not None and raw_loss > 0 else 1.0

    splits: list[dict[str, Any]] = []
    start_d, start_t = points[0].distance_m, points[0].t_s
    boundary = start_d + SPLIT_LENGTH_M
    gain = loss = 0.0
    hrs: list[int] = []

    def close(end_d: float, end_t: float) -> None:
        nonlocal start_d, start_t, gain, loss, hrs
        splits.append(
            {
                "kind": LapKind.km,
                "index": len(splits),
                "start_distance_m": start_d,
                "end_distance_m": end_d,
                "duration_s": end_t - start_t,
                "elevation_gain_m": round(gain * gain_scale, 1),
                "elevation_loss_m": round(loss * loss_scale, 1),
                "avg_hr": round(fmean(hrs)) if hrs else None,
            }
        )
        start_d, start_t, gain, loss, hrs = end_d, end_t, 0.0, 0.0, []

    for i in range(1, len(points)):
        p = points[i]
        while p.distance_m >= boundary:
            close(boundary, _time_at(points, i, boundary))
            boundary += SPLIT_LENGTH_M
        gain += gains[i]
        loss += losses[i]
        if p.hr is not None:
            hrs.append(p.hr)

    last = points[-1]
    if last.distance_m - start_d >= 1:  # dernier bout de plus d'1 m
        close(last.distance_m, last.t_s)

    trace["inputs"] = {
        "points": len(points),
        "fit_gain_m": round(raw_gain, 1),
        "fit_loss_m": round(raw_loss, 1),
        "garmin_gain_m": total_gain_m,
        "garmin_loss_m": total_loss_m,
    }
    return splits, trace


def compute(db: Session, activity: Activity, rules: ActivityCategories | None = None) -> None:
    """Calcule et enregistre catégorie, km-effort et splits par km d'une activité."""
    rules = rules or settings.get(db, ActivityCategories)
    distance = activity.distance_m or 0.0
    gain = activity.elevation_gain_m or 0.0

    category, category_trace = classify(activity.activity_type, distance, gain, rules)
    activity.category = category
    activity.km_effort = round(km_effort(distance, gain), 2)

    points = list(
        db.scalars(
            select(ActivityPoint)
            .where(ActivityPoint.activity_id == activity.id)
            .order_by(ActivityPoint.seq)
        )
    )
    splits, splits_trace = km_splits(points, activity.elevation_gain_m, activity.elevation_loss_m)
    db.execute(
        delete(ActivityLap).where(
            ActivityLap.activity_id == activity.id, ActivityLap.kind == LapKind.km
        )
    )
    if splits:
        db.execute(insert(ActivityLap), [{"activity_id": activity.id, **s} for s in splits])

    activity.calc_trace = {
        "version": METRICS_VERSION,
        "category": category_trace,
        "km_effort": {
            "method": "distance_km_plus_dplus_over_100",
            "inputs": {"distance_m": distance, "elevation_gain_m": gain},
        },
        "km_splits": splits_trace,
    }
