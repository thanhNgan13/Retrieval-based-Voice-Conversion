from src.config.celery_app import celery_app
from src.services.song_infer_executor import execute_song_infer_job


@celery_app.task(name="infer_song_cover")
def infer_song_cover_task(song_infer_job_id: str) -> None:
    execute_song_infer_job(song_infer_job_id)
