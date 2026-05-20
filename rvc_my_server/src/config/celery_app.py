from celery import Celery

from src.config.settings import settings


def _broker_url() -> str:
    return settings.CELERY_BROKER_URL or settings.REDIS_URL


def _backend_url() -> str:
    return settings.CELERY_RESULT_BACKEND or settings.REDIS_URL


celery_app = Celery(
    "rvc_my_server",
    broker=_broker_url(),
    backend=_backend_url(),
    include=["src.tasks.train_tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    timezone="UTC",
)
