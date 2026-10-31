"""Faux Garmin pour les tests : liste d'activités, FIT synthétiques, erreurs à la demande."""

import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import Event, EventType, FileType, Manufacturer
from garmin_personal_api import HttpError

START = datetime(2026, 10, 25, 8, 0, 0, tzinfo=UTC)


def _timer_event(timestamp: int, kind: EventType) -> EventMessage:
    event = EventMessage()
    event.timestamp = timestamp
    event.event = Event.TIMER
    event.event_type = kind
    return event


def build_fit(
    points: int = 10,
    lap_every: int = 5,
    *,
    zipped: bool = True,
    pause_after: int | None = None,
    pause_s: int = 0,
) -> bytes:
    """FIT d'une sortie : 1 point par seconde, 3 m/s, +1 m d'altitude par point.

    pause_after / pause_s : chrono arrêté après ce point pendant pause_s secondes.
    """
    t0 = int(START.timestamp() * 1000)
    builder = FitFileBuilder(auto_define=True)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.time_created = t0
    builder.add(file_id)
    builder.add(_timer_event(t0, EventType.START))

    def ts(i: int) -> int:
        shift = pause_s if pause_after is not None and i > pause_after else 0
        return t0 + (i + shift) * 1000

    for i in range(points):
        record = RecordMessage()
        record.timestamp = ts(i)
        record.position_lat = 45.0 + i * 1e-4
        record.position_long = 6.0
        record.altitude = 100.0 + i
        record.distance = i * 3.0
        record.speed = 3.0
        record.heart_rate = 140 + i % 50
        record.cadence = 80
        builder.add(record)
        if i == pause_after:
            builder.add(_timer_event(ts(i), EventType.STOP_ALL))
            builder.add(_timer_event(ts(i) + pause_s * 1000, EventType.START))
    for lap_start in range(0, points - 1, lap_every):
        lap_end = min(lap_start + lap_every, points - 1)
        lap = LapMessage()
        lap.start_time = t0 + lap_start * 1000
        lap.timestamp = t0 + lap_end * 1000
        lap.total_timer_time = float(lap_end - lap_start)
        lap.total_elapsed_time = float(lap_end - lap_start)
        lap.total_distance = (lap_end - lap_start) * 3.0
        lap.total_ascent = lap_end - lap_start
        lap.total_descent = 0
        lap.avg_heart_rate = 150
        builder.add(lap)
    content = builder.build().to_bytes()
    if not zipped:
        return content
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("1_ACTIVITY.fit", content)
    return buffer.getvalue()


def summary(garmin_id: int, type_key: str = "running", days_ago: int = 0) -> dict[str, Any]:
    start = START - timedelta(days=days_ago)
    return {
        "activityId": garmin_id,
        "activityName": f"Sortie {garmin_id}",
        "activityType": {"typeKey": type_key},
        "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S"),
        "startTimeLocal": (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "distance": 10000.0,
        "duration": 3000.0,
        "movingDuration": 2950.0,
        "elevationGain": 120.0,
        "elevationLoss": 118.0,
        "averageHR": 150.4,
        "maxHR": 180.0,
        "hrTimeInZone_1": 60.0,
        "hrTimeInZone_2": 600.0,
        "hrTimeInZone_3": 1200.0,
        "hrTimeInZone_4": 900.0,
        "hrTimeInZone_5": 240.0,
        "locationName": "Grenoble",
    }


class FakeGarminApi:
    """État partagé du faux Garmin ; FakeClient le lit à chaque appel."""

    def __init__(self) -> None:
        self.activities: list[dict[str, Any]] = []  # les plus récentes d'abord, comme Garmin
        self.fits: dict[int, bytes] = {}
        self.search_calls: list[int] = []
        self.downloads: list[int] = []
        self.errors: list[int] = []  # codes HTTP à renvoyer aux prochains appels
        # Santé, par date ISO ; health_calls garde (méthode, début, fin) de chaque appel.
        self.nights: dict[str, dict[str, Any]] = {}
        self.days: dict[str, dict[str, Any]] = {}
        self.weighings: list[dict[str, Any]] = []
        self.hrv: dict[str, dict[str, Any]] = {}
        self.health_calls: list[tuple[str, date, date]] = []
        self.health_limit: int | None = None  # HTTP 429 au-delà de ce nombre d'appels santé

    def _maybe_fail(self, path: str) -> None:
        if self.errors:
            code = self.errors.pop(0)
            raise HttpError(status_code=code, method="GET", url=path, response_text="")

    def client(self, token: str, **_: Any) -> "FakeClient":
        return FakeClient(self)


class FakeClient:
    def __init__(self, api: FakeGarminApi) -> None:
        self.api = api

    def search_activities(self, *, start: int = 0, limit: int = 20, **_: Any) -> list[Any]:
        self.api._maybe_fail("/activities")
        self.api.search_calls.append(start)
        return self.api.activities[start : start + limit]

    def download_activity(self, activity_id: int | str) -> bytes:
        self.api._maybe_fail("/download")
        self.api.downloads.append(int(activity_id))
        return self.api.fits.get(int(activity_id)) or build_fit()

    def _health(self, name: str, start: date, end: date, items: dict[str, Any]) -> list[Any]:
        self.api._maybe_fail(f"/{name}")
        if (
            self.api.health_limit is not None
            and len(self.api.health_calls) >= self.api.health_limit
        ):
            raise HttpError(status_code=429, method="GET", url=f"/{name}", response_text="")
        self.api.health_calls.append((name, start, end))
        return [
            v for d, v in sorted(items.items()) if start.isoformat() <= d[:10] <= end.isoformat()
        ]

    def get_daily_sleep_summaries(self, start: date, end: date) -> list[Any]:
        return self._health("sleep", start, end, self.api.nights)

    def get_daily_summaries(self, start: date, end: date) -> dict[str, Any]:
        return {"data": self._health("summaries", start, end, self.api.days)}

    def get_daily_hrv_summaries(self, start: date, end: date) -> Any:
        items = self._health("hrv", start, end, self.api.hrv)
        return {"hrvSummaries": items} if items else None  # Garmin : None sans VFC

    def get_weight_measurements(self, start: date, end: date) -> dict[str, Any]:
        weighings = {f"{w['calendarDate']}#{w['samplePk']}": w for w in self.api.weighings}
        samples = self._health("weight", start, end, weighings)
        return {"dailyWeightSummaries": [{"allWeightMetrics": samples}] if samples else []}

    def close(self) -> None:
        pass


def night(day: str, total_s: int = 27000, score: int | None = 80) -> dict[str, Any]:
    return {
        "calendarDate": day,
        "sleepTimeSeconds": total_s,
        "deepSleepSeconds": 5400,
        "lightSleepSeconds": 14400,
        "remSleepSeconds": 7200,
        "awakeSleepSeconds": 600,
        "sleepStartTimestampGMT": 1792794780000,
        "sleepEndTimestampGMT": 1792820160000,
        "avgHeartRate": None,
        "sleepScores": {"overall": {"value": score, "qualifierKey": "GOOD"}},
    }


def daily_summary(day: str, steps: int = 9000, resting_hr: int = 50) -> dict[str, Any]:
    return {
        "calendarDate": day,
        "movement": {"steps": {"goal": 9000, "value": steps}},
        "heartRate": {"minValue": 45, "maxValue": 150, "restingValue": resting_hr},
        "bodyBattery": {"minValue": 15, "maxValue": 80, "latestValue": 20},
    }


def weighing(sample_id: int, day: str, grams: float = 70500.0) -> dict[str, Any]:
    return {
        "samplePk": sample_id,
        "calendarDate": day,
        "timestampGMT": 1792794780000,
        "weight": grams,
        "sourceType": "MANUAL",
    }
