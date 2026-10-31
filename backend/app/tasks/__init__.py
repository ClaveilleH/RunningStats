"""Toutes les tâches de fond, importées ici pour être enregistrées auprès de app.jobs."""

from app.tasks import maintenance

__all__ = ["maintenance"]
