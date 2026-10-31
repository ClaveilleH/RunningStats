"""Toutes les tâches de fond, importées ici pour être enregistrées auprès de app.jobs."""

from app.tasks import garmin_health, garmin_keys, garmin_sync, maintenance, recompute

__all__ = ["garmin_health", "garmin_keys", "garmin_sync", "maintenance", "recompute"]
