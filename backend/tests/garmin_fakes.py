"""Faux Garmin pour les tests : liste d'activités, FIT synthétiques, erreurs à la demande."""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import FileType, Manufacturer
from garmin_personal_api import HttpError

START = datetime(2026, 10, 25, 8, 0, 0, tzinfo=UTC)


def build_fit(points: int = 10, lap_every: int = 5, *, zipped: bool = True) -> bytes:
    """FIT d'une sortie : 1 point par seconde, 3 m/s, +1 m d'altitude par point."""
    t0 = int(START.timestamp() * 1000)
    builder = FitFileBuilder(auto_define=True)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.time_created = t0
    builder.add(file_id)
    for i in range(points):
        record = RecordMessage()
        record.timestamp = t0 + i * 1000
        record.position_lat = 45.0 + i * 1e-4
        record.position_long = 6.0
        record.altitude = 100.0 + i
        record.distance = i * 3.0
        record.speed = 3.0
        record.heart_rate = 140 + i
        record.cadence = 80
        builder.add(record)
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

    def close(self) -> None:
        pass
