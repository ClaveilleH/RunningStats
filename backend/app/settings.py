"""Réglages métier du groupe (table app_settings), modifiables par l'admin.

Chaque réglage est un modèle Pydantic : ses valeurs par défaut sont celles de la doc de
conception, et la base ne garde que ce que l'admin a changé. À ne pas confondre avec
app/config.py (configuration technique lue dans l'environnement).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.models import AppSetting


class SettingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = ""  # surchargé par chaque réglage


class ActivityCategories(SettingModel):
    """Classement route / trail d'une sortie (doc « Prédiction et conseils », §3)."""

    key: str = "activity_categories"
    # D+ par km sous lequel une sortie compte comme route.
    road_max_dplus_per_km: float = Field(default=10, ge=0)
    # D+ par km à partir duquel une sortie compte comme trail ; entre les deux : mixte.
    trail_min_dplus_per_km: float = Field(default=25, ge=0)
    # Taille d'effort (km-effort) à partir de laquelle un trail est long.
    # Valeur non fixée par la doc : 42 km-effort (équivalent marathon) en attendant.
    long_trail_min_km_effort: float = Field(default=42, gt=0)

    @model_validator(mode="after")
    def thresholds_in_order(self) -> "ActivityCategories":
        if self.road_max_dplus_per_km > self.trail_min_dplus_per_km:
            raise ValueError("Le seuil route doit être inférieur ou égal au seuil trail.")
        return self


class SyncSchedule(SettingModel):
    """Synchro Garmin automatique (doc « Besoins du back », tâches de fond)."""

    key: str = "sync_schedule"
    # Fréquence du groupe ; un membre peut avoir la sienne (users.sync_interval_minutes).
    interval_minutes: int = Field(default=60, ge=10, le=24 * 60)
    # Pas de synchro automatique pendant la nuit (heures du fuseau du groupe).
    night_start_hour: int = Field(default=0, ge=0, le=23)
    night_end_hour: int = Field(default=6, ge=0, le=23)
    # Jour d'une course : fréquence pour les inscrits (active quand les courses existeront).
    race_day_interval_minutes: int = Field(default=10, ge=5, le=24 * 60)


class Readiness(SettingModel):
    """Forme avant une sortie (doc « Prédiction et conseils », §6, étape 3)."""

    key: str = "readiness"
    # Poids (%) des 3 nuits précédentes, de la veille à l'avant-avant-veille.
    sleep_weights: list[float] = Field(default=[50, 30, 20], min_length=1, max_length=7)
    # FC au repos du jour comparée à la moyenne des N jours d'avant.
    # Valeur non fixée par la doc : 7 jours, comme la moyenne Garmin des Réglages.
    resting_hr_baseline_days: int = Field(default=7, ge=1, le=60)

    @model_validator(mode="after")
    def weights_are_positive(self) -> "Readiness":
        if any(w < 0 for w in self.sleep_weights) or sum(self.sleep_weights) <= 0:
            raise ValueError("Les poids du sommeil doivent être positifs.")
        return self


REGISTRY: dict[str, type[SettingModel]] = {
    model.model_fields["key"].default: model
    for model in (ActivityCategories, SyncSchedule, Readiness)
}


def get[S: SettingModel](db: Session, model: type[S]) -> S:
    row = db.get(AppSetting, model.model_fields["key"].default)
    values = row.value if row else {}
    return model.model_validate(values)


def all_settings(db: Session) -> dict[str, dict[str, Any]]:
    return {key: get(db, model).model_dump(exclude={"key"}) for key, model in REGISTRY.items()}


def save(db: Session, key: str, values: dict[str, Any]) -> SettingModel:
    """Valide puis enregistre un réglage complet. Lève KeyError ou ValidationError."""
    model = REGISTRY[key]
    validated = model.model_validate(values)
    stored = validated.model_dump(exclude={"key"})
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=stored))
    else:
        row.value = stored
    db.flush()
    return validated
