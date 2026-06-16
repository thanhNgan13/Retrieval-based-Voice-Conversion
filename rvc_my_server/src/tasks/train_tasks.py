from src.config.celery_app import celery_app
from src.services.train_service import execute_train_job


@celery_app.task(name="train_rvc_model")
def train_rvc_model_task(train_job_id: str) -> None:
    try:
        execute_train_job(train_job_id)
    finally:
        from src.services import resource_manager
        from src.services.job_scheduler import trigger_scheduler

        resource_manager.release(train_job_id)
        trigger_scheduler()
