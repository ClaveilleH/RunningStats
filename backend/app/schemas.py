from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field
from pydantic_core import PydanticCustomError

from app.models import GarminSource, GarminStatus, JobStatus, Role
from app.security import MIN_PASSWORD_LENGTH


def _check_password_length(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        # Message en français, affiché tel quel par le front.
        raise PydanticCustomError(
            "password_too_short",
            "Le mot de passe doit faire au moins {min_length} caractères.",
            {"min_length": MIN_PASSWORD_LENGTH},
        )
    return value


Password = Annotated[str, Field(max_length=200), AfterValidator(_check_password_length)]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class AcceptInvitationIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: Password


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: Password


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    username: str | None
    email: str
    role: Role
    theme: str


class InvitationCheckOut(BaseModel):
    valid: bool
    expires_at: datetime
    min_password_length: int


class InvitationOut(BaseModel):
    token: str
    expires_at: datetime


class GarminKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=2000)
    # Date de fin de validité affichée par Garmin à la création de la clé (facultative).
    api_key_expires_on: date | None = None


class GarminOut(BaseModel):
    connected: bool
    source: GarminSource | None = None
    status: GarminStatus | None = None
    api_key_expires_at: datetime | None = None
    key_expires_soon: bool = False
    last_sync_at: datetime | None = None
    last_error: str | None = None
    # Fréquence de la synchro auto : celle du membre, sinon celle du groupe.
    sync_interval_minutes: int | None = None
    # Synchro en file ou en cours (celle lancée par l'enregistrement de la clé, par exemple).
    sync_job_id: int | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: JobStatus
    user_id: int | None
    attempts: int
    error: str | None
    created_at: datetime
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobStartedOut(BaseModel):
    """Réponse 202 d'une route qui lance une tâche longue."""

    job_id: int


class ActivityItemOut(BaseModel):
    """Une ligne de la liste des activités."""

    id: int
    name: str | None
    activity_type: str
    category: str | None
    start_time: datetime
    # Heure de la montre, sans fuseau : c'est elle qu'on affiche.
    start_time_local: datetime
    location_name: str | None
    distance_m: float | None
    duration_s: float | None  # temps chrono, pauses exclues
    elevation_gain_m: float | None
    avg_hr: int | None
    pace_s_per_km: float | None
    pinned: bool
    # Tracé simplifié [lat, lon] pour la vue cartes (si demandé).
    track: list[list[float]] | None = None


class ActivitySummaryOut(BaseModel):
    count: int
    distance_m: float
    elevation_gain_m: float
    duration_s: float


class ActivityListOut(BaseModel):
    items: list[ActivityItemOut]
    total: int
    page: int
    page_size: int
    # Totaux de toute la sélection (filtres appliqués), pas seulement de la page.
    summary: ActivitySummaryOut


class WeekOut(BaseModel):
    week_start: date
    count: int
    distance_m: float
    elevation_gain_m: float
    current: bool


class SplitOut(BaseModel):
    """Un tour de la montre ou un split par km."""

    model_config = ConfigDict(from_attributes=True)

    index: int
    start_distance_m: float | None
    end_distance_m: float | None
    duration_s: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    avg_hr: int | None


class ActivityDetailsOut(BaseModel):
    elapsed_s: float | None
    stopped_s: float | None
    avg_cadence_spm: float | None
    calories: float | None
    min_altitude_m: float | None
    max_altitude_m: float | None


class ActivityOut(ActivityItemOut):
    """Fiche d'une activité."""

    user_id: int
    moving_duration_s: float | None
    elevation_loss_m: float | None
    max_hr: int | None
    km_effort: float | None
    # Secondes en zones FC 1 à 5, selon Garmin.
    hr_zones_s: list[float] | None
    details: ActivityDetailsOut
    km_splits: list[SplitOut]
    laps: list[SplitOut]
    # Faux tant que le FIT n'a pas été lu : pas encore de points ni de splits.
    processed: bool


class ActivityPointsOut(BaseModel):
    """Points allégés, en colonnes de même longueur."""

    step_m: float
    distance_m: list[float | None]
    timer_s: list[float | None]
    lat: list[float | None]
    lon: list[float | None]
    altitude_m: list[float | None]
    hr: list[int | None]
    cadence_spm: list[int | None]
    pace_s_per_km: list[float | None]
