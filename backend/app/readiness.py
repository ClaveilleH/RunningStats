"""Forme avant une sortie : sommeil des nuits précédentes pondéré, FC au repos, Body Battery."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import settings
from app.models import Activity, DailyHealth, SleepNight
from app.settings import Readiness

READINESS_VERSION = 1


def _sleep_day(db: Session, activity: Activity) -> date:
    """Date (de réveil) de la dernière nuit avant la sortie.

    Garmin date une nuit du jour du réveil. Une sortie du matin a donc pour veille la nuit
    du même jour ; une sortie partie avant la fin de cette nuit (course de nuit) prend
    celle d'avant.
    """
    day = activity.start_time_local.date()
    night = db.scalar(
        select(SleepNight).where(SleepNight.user_id == activity.user_id, SleepNight.date == day)
    )
    if night and night.end_time and night.end_time > activity.start_time:
        return day - timedelta(days=1)
    return day


def compute(db: Session, activity: Activity) -> dict[str, Any]:
    rules = settings.get(db, Readiness)
    last = _sleep_day(db, activity)
    days = [last - timedelta(days=i) for i in range(len(rules.sleep_weights))]
    nights_by_day = {
        n.date: n
        for n in db.scalars(
            select(SleepNight).where(
                SleepNight.user_id == activity.user_id, SleepNight.date.in_(days)
            )
        )
    }

    nights = []
    weighted = 0.0
    used_weight = 0.0
    for day, weight in zip(days, rules.sleep_weights, strict=True):
        night = nights_by_day.get(day)
        nights.append(
            {
                "date": day,
                "total_s": night.total_s if night else None,
                "score": night.score if night else None,
                "weight": weight,
            }
        )
        if night and night.score is not None:
            weighted += night.score * weight
            used_weight += weight
    # Nuit manquante : les poids des nuits connues sont remis à l'échelle.
    sleep_score = round(weighted / used_weight) if used_weight else None

    day = activity.start_time_local.date()
    baseline_start = day - timedelta(days=rules.resting_hr_baseline_days)
    health = {
        h.date: h
        for h in db.scalars(
            select(DailyHealth).where(
                DailyHealth.user_id == activity.user_id,
                DailyHealth.date >= baseline_start,
                DailyHealth.date <= day,
            )
        )
    }
    today = health.get(day)
    resting_hr = today.resting_hr if today else None
    baseline_values = [
        h.resting_hr for d, h in health.items() if d < day and h.resting_hr is not None
    ]
    baseline = sum(baseline_values) / len(baseline_values) if baseline_values else None
    resting_hr_delta = (
        round(resting_hr - baseline) if resting_hr is not None and baseline is not None else None
    )

    return {
        "nights": nights,
        "sleep_score": sleep_score,
        "resting_hr": resting_hr,
        "resting_hr_baseline": round(baseline, 1) if baseline is not None else None,
        "resting_hr_delta": resting_hr_delta,
        # Garmin ne donne que le min et le max du jour : le max est atteint au réveil.
        "body_battery_max": today.body_battery_max if today else None,
        "trace": {
            "method": "readiness",
            "version": READINESS_VERSION,
            "params": rules.model_dump(exclude={"key"}),
            "inputs": {
                "activity_day": day.isoformat(),
                "last_night": last.isoformat(),
                "sleep_weight_used": used_weight,
                "resting_hr_baseline_days_found": len(baseline_values),
            },
        },
    }
