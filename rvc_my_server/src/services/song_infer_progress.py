import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis

from src.config.settings import settings
from src.models.song_infer_job_model import (
    get_song_infer_job_by_id,
    update_song_infer_job_in_firestore,
)

logger = logging.getLogger(__name__)


def song_infer_channel(song_infer_job_id: str) -> str:
    return f"rvc_song_infer_job:{song_infer_job_id}"


def _parse_timestamp(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _elapsed_ms(song_infer_job_id: str, extra_updates: Optional[dict]) -> int:
    started_at = (extra_updates or {}).get("started_at")
    if not started_at:
        doc = get_song_infer_job_by_id(song_infer_job_id) or {}
        started_at = doc.get("started_at")
    started_dt = _parse_timestamp(started_at)
    if not started_dt:
        return 0
    return max(0, int((datetime.now(timezone.utc) - started_dt).total_seconds() * 1000))


def publish_song_infer_progress(
    song_infer_job_id: str,
    status: str,
    stage: str,
    progress: int,
    message: str,
    outputs: Optional[dict] = None,
    error: str = "",
    extra_updates: Optional[dict] = None,
) -> None:
    elapsed_ms = _elapsed_ms(song_infer_job_id, extra_updates)
    payload = {
        "songInferJobId": song_infer_job_id,
        "status": status,
        "stage": stage,
        "progress": max(0, min(100, int(progress))),
        "elapsedMs": elapsed_ms,
        "message": message,
        "outputs": outputs or {},
        "error": error,
    }

    updates = {
        "status": status,
        "stage": stage,
        "progress": payload["progress"],
        "elapsed_ms": elapsed_ms,
        "message": message,
        "error": error,
    }
    if outputs is not None:
        updates["outputs"] = outputs
    if extra_updates:
        updates.update(extra_updates)

    update_song_infer_job_in_firestore(song_infer_job_id, updates)

    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.publish(song_infer_channel(song_infer_job_id), json.dumps(payload))
        client.close()
    except Exception:
        logger.warning(
            "Failed to publish song infer progress for %s",
            song_infer_job_id,
            exc_info=True,
        )
