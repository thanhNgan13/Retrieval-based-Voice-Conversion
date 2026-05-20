from src.config.celery_app import celery_app
from src.services.train_service import execute_train_job


@celery_app.task(name="train_rvc_model")
def train_rvc_model_task(train_job_id: str) -> None:
    execute_train_job(train_job_id)
