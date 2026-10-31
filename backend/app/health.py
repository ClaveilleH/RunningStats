"""Conversion des réponses santé de Garmin en lignes de sleep_nights, weights et daily_health."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import DailyHealth, SleepNight, Weight

# Périodes maximales acceptées par Garmin pour un appel (mesurées le 31/10/2026).
# Les pas sont dans les résumés du jour : l'appel « pas » (28 j max) est inutile.
SLEEP_MAX_DAYS = 31
SUMMARIES_MAX_DAYS = 366
WEIGHT_MAX_DAYS = 3 * 366
HRV_MAX_DAYS = 366  # accepté, mais la VFC revient vide sur la montre testée


def _ms_to_datetime(value: Any) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, UTC) if isinstance(value, int | float) else None


def _int(value: Any) -> int | None:
    return round(value) if isinstance(value, int | float) else None


def sleep_rows(user_id: int, summaries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = []
    for night in summaries or []:
        if not night.get("calendarDate") or not night.get("sleepTimeSeconds"):
            continue  # jour sans nuit enregistrée
        score = ((night.get("sleepScores") or {}).get("overall") or {}).get("value")
        rows.append(
            {
                "user_id": user_id,
                "date": date.fromisoformat(night["calendarDate"]),
                "start_time": _ms_to_datetime(night.get("sleepStartTimestampGMT")),
                "end_time": _ms_to_datetime(night.get("sleepEndTimestampGMT")),
                "total_s": night.get("sleepTimeSeconds"),
                "deep_s": night.get("deepSleepSeconds"),
                "light_s": night.get("lightSleepSeconds"),
                "rem_s": night.get("remSleepSeconds"),
                "awake_s": night.get("awakeSleepSeconds"),
                "score": _int(score),
                "avg_hr": _int(night.get("avgHeartRate")),
                "raw": night,
            }
        )
    return rows


def weight_rows(user_id: int, response: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for day in (response or {}).get("dailyWeightSummaries") or []:
        for sample in day.get("allWeightMetrics") or []:
            if sample.get("weight") is None or sample.get("samplePk") is None:
                continue
            rows.append(
                {
                    "user_id": user_id,
                    "garmin_sample_id": sample["samplePk"],
                    "date": date.fromisoformat(sample["calendarDate"]),
                    "measured_at": _ms_to_datetime(sample.get("timestampGMT")),
                    "weight_kg": round(sample["weight"] / 1000, 2),  # Garmin : grammes
                }
            )
    return rows


def _hrv_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        return response.get("hrvSummaries") or []
    return response if isinstance(response, list) else []


def daily_rows(user_id: int, summaries: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Pas, FC au repos et Body Battery depuis les résumés du jour."""
    rows = []
    for day in (summaries or {}).get("data") or []:
        battery = day.get("bodyBattery") or {}
        values = {
            "steps": _int(((day.get("movement") or {}).get("steps") or {}).get("value")),
            "resting_hr": _int((day.get("heartRate") or {}).get("restingValue")),
            "body_battery_min": _int(battery.get("minValue")),
            "body_battery_max": _int(battery.get("maxValue")),
        }
        if any(v is not None for v in values.values()):
            rows.append(
                {"user_id": user_id, "date": date.fromisoformat(day["calendarDate"]), **values}
            )
    return rows


def hrv_rows(user_id: int, response: Any) -> list[dict[str, Any]]:
    """VFC moyenne de la nuit. Format supposé (non vu : la montre testée n'en a pas)."""
    if isinstance(response, dict):
        items = response.get("hrvSummaries") or []
    else:
        items = response if isinstance(response, list) else []
    return [
        {
            "user_id": user_id,
            "date": date.fromisoformat(item["calendarDate"]),
            "hrv_ms": item["lastNightAvg"],
        }
        for item in items
        if isinstance(item, dict)
        and item.get("calendarDate")
        and isinstance(item.get("lastNightAvg"), int | float)
    ]


def _upsert(db: Session, model: type, rows: list[dict[str, Any]], keys: list[str]) -> None:
    if not rows:
        return
    # Une même clé deux fois ferait échouer l'upsert : on garde la dernière.
    rows = list({tuple(row[k] for k in keys): row for row in rows}.values())
    # Seules les colonnes fournies sont mises à jour : la VFC n'efface pas les pas.
    stmt = insert(model).values(rows)
    columns = set(rows[0]) - set(keys)
    db.execute(
        stmt.on_conflict_do_update(index_elements=keys, set_={c: stmt.excluded[c] for c in columns})
    )


def store_sleep(db: Session, rows: list[dict[str, Any]]) -> None:
    _upsert(db, SleepNight, rows, ["user_id", "date"])


def store_weights(db: Session, rows: list[dict[str, Any]]) -> None:
    _upsert(db, Weight, rows, ["user_id", "garmin_sample_id"])


def store_daily(db: Session, rows: list[dict[str, Any]]) -> None:
    """Lignes de daily_rows ou de hrv_rows (mêmes colonnes dans une même liste)."""
    _upsert(db, DailyHealth, rows, ["user_id", "date"])


def chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Découpe [start, end] (inclus) en périodes acceptées par Garmin."""
    periods = []
    while start <= end:
        stop = min(end, start + timedelta(days=max_days - 1))
        periods.append((start, stop))
        start = stop + timedelta(days=1)
    return periods
