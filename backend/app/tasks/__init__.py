"""Toutes les tâches de fond, importées ici pour être enregistrées auprès de app.jobs."""

from app.tasks import garmin_keys, garmin_sync, maintenance, recompute

__all__ = ["garmin_keys", "garmin_sync", "maintenance", "recompute"]
