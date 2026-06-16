from src.config.celery_app import celery_app
from src.services.song_infer_executor import execute_song_infer_job


@celery_app.task(name="infer_song_cover")
def infer_song_cover_task(song_infer_job_id: str) -> None:
    try:
        execute_song_infer_job(song_infer_job_id)
    finally:
        from src.services import resource_manager
        from src.services.job_scheduler import trigger_scheduler

        resource_manager.release(song_infer_job_id)
        trigger_scheduler()
