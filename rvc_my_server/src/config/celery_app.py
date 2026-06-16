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
    include=["src.tasks.train_tasks", "src.tasks.song_infer_tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    # Fetch only one task at a time so the scheduler (not Celery) controls concurrency.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    timezone="UTC",
    # Allow multiple tasks to run concurrently inside one worker process.
    # Start the worker with --pool=threads --concurrency=N to match this value.
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
)
