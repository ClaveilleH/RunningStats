"""Lecture des fichiers FIT téléchargés depuis Garmin (zip contenant un .fit)."""

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import fitdecode

SEMICIRCLE_TO_DEG = 180 / 2**31


@dataclass
class ParsedFit:
    points: list[dict[str, Any]] = field(default_factory=list)
    laps: list[dict[str, Any]] = field(default_factory=list)


def fit_bytes(content: bytes) -> bytes:
    """Garmin renvoie un zip ; on accepte aussi un .fit nu (import manuel)."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".fit")]
        if not names:
            raise ValueError("Aucun fichier .fit dans l'archive Garmin.")
        return archive.read(names[0])


def _deg(value: Any) -> float | None:
    return value * SEMICIRCLE_TO_DEG if isinstance(value, int | float) else None


def _first(values: dict[str, Any], *names: str) -> Any:
    for name in names:
        if values.get(name) is not None:
            return values[name]
    return None


def _cadence_spm(values: dict[str, Any]) -> int | None:
    # En course, le FIT compte les cycles d'une jambe : x 2 pour avoir des pas par minute.
    cadence = values.get("cadence")
    if cadence is None:
        return None
    return round((cadence + (values.get("fractional_cadence") or 0)) * 2)


TIMER_STOPS = {"stop", "stop_all", "stop_disable", "stop_disable_all"}


def parse(content: bytes) -> ParsedFit:
    parsed = ParsedFit()
    first_ts: datetime | None = None
    lap_start_distance = 0.0
    # Pauses du chrono, lues dans les événements « timer » du FIT.
    paused_since: datetime | None = None
    paused_total = 0.0
    try:
        reader = fitdecode.FitReader(io.BytesIO(fit_bytes(content)))
        with reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                values = {f.name: f.value for f in frame.fields if f.value is not None}
                if frame.name == "event" and values.get("event") == "timer":
                    ts, kind = values.get("timestamp"), values.get("event_type")
                    if kind in TIMER_STOPS and paused_since is None:
                        paused_since = ts
                    elif kind == "start" and paused_since is not None and ts is not None:
                        paused_total += (ts - paused_since).total_seconds()
                        paused_since = None
                elif frame.name == "record" and values.get("timestamp") is not None:
                    ts = values["timestamp"]
                    first_ts = first_ts or ts
                    elapsed = (ts - first_ts).total_seconds()
                    # Pendant une pause (souvent un point au moment de l'arrêt), le chrono est figé.
                    paused_now = (
                        max(0.0, (ts - paused_since).total_seconds()) if paused_since else 0.0
                    )
                    parsed.points.append(
                        {
                            "seq": len(parsed.points),
                            "t_s": elapsed,
                            "timer_s": elapsed - paused_total - paused_now,
                            "lat": _deg(values.get("position_lat")),
                            "lon": _deg(values.get("position_long")),
                            "altitude_m": _first(values, "enhanced_altitude", "altitude"),
                            "distance_m": values.get("distance"),
                            "speed_ms": _first(values, "enhanced_speed", "speed"),
                            "hr": values.get("heart_rate"),
                            "cadence_spm": _cadence_spm(values),
                        }
                    )
                elif frame.name == "lap":
                    distance = values.get("total_distance")
                    parsed.laps.append(
                        {
                            "index": len(parsed.laps),
                            "start_distance_m": lap_start_distance,
                            "end_distance_m": (
                                lap_start_distance + distance if distance is not None else None
                            ),
                            "duration_s": _first(values, "total_timer_time", "total_elapsed_time"),
                            "elevation_gain_m": values.get("total_ascent"),
                            "elevation_loss_m": values.get("total_descent"),
                            "avg_hr": values.get("avg_heart_rate"),
                        }
                    )
                    lap_start_distance += distance or 0.0
    except fitdecode.FitError as e:
        raise ValueError(f"Fichier FIT illisible : {e}") from e
    return parsed
