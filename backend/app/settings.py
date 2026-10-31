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


REGISTRY: dict[str, type[SettingModel]] = {
    model.model_fields["key"].default: model for model in (ActivityCategories,)
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
