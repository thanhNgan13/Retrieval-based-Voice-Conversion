import json
import logging
from typing import Optional

import redis

from src.config.settings import settings
from src.models.train_job_model import update_train_job_in_firestore

logger = logging.getLogger(__name__)


def _channel(train_job_id: str) -> str:
    return f"rvc_train_job:{train_job_id}"


def publish_train_progress(
    train_job_id: str,
    status: str,
    stage: str,
    progress: int,
    message: str,
    rvc_model_id: str = "",
    error: str = "",
    extra_updates: Optional[dict] = None,
) -> None:
    payload = {
        "trainJobId": train_job_id,
        "status": status,
        "stage": stage,
        "progress": max(0, min(100, int(progress))),
        "message": message,
        "rvcModelId": rvc_model_id,
        "error": error,
    }

    updates = {
        "status": status,
        "stage": stage,
        "progress": payload["progress"],
        "message": message,
        "rvc_model_id": rvc_model_id,
        "error": error,
    }
    if extra_updates:
        updates.update(extra_updates)

    update_train_job_in_firestore(train_job_id, updates)

    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.publish(_channel(train_job_id), json.dumps(payload))
        client.close()
    except Exception:
        logger.warning("Failed to publish train progress for %s", train_job_id, exc_info=True)
