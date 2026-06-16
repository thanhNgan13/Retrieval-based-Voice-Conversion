"""Redis-backed GPU VRAM resource manager for the job scheduler.

Tracks how much VRAM (in MB) has been promised to running/dispatched jobs via a
Redis hash `scheduler:job_allocations`.  The scheduler calls `try_allocate`
before dispatching a Celery task; each Celery task calls `release` in its
finally-block when the job finishes.

Design notes:
- Total VRAM budget = GPU total (from torch.cuda) or FALLBACK_TOTAL_VRAM_MB.
- We track *promised* VRAM (what we've budgeted), NOT actual fragmented memory,
  so the accounting stays clean even as models are loaded/unloaded.
- `try_allocate` is atomic via Redis WATCH/MULTI/EXEC to prevent race conditions
  when multiple scheduler instances run.
"""
import logging

import redis

from src.config.settings import settings

logger = logging.getLogger(__name__)

_ALLOC_KEY = "scheduler:job_allocations"  # Redis Hash: {job_id -> vram_mb_str}

_cached_total_vram_mb: int | None = None


def _get_total_vram_mb() -> int:
    global _cached_total_vram_mb
    if _cached_total_vram_mb is None:
        try:
            import torch
            if torch.cuda.is_available():
                _, total = torch.cuda.mem_get_info(0)
                _cached_total_vram_mb = total // (1024 * 1024)
                logger.info("GPU total VRAM: %d MB", _cached_total_vram_mb)
            else:
                _cached_total_vram_mb = settings.FALLBACK_TOTAL_VRAM_MB
                logger.info("No CUDA — using fallback VRAM budget: %d MB", _cached_total_vram_mb)
        except Exception:
            _cached_total_vram_mb = settings.FALLBACK_TOTAL_VRAM_MB
    return _cached_total_vram_mb


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def try_allocate(job_id: str, vram_mb: int) -> bool:
    """Atomically reserve `vram_mb` for `job_id`.

    Returns True and writes the allocation to Redis if there is enough budget.
    Returns False without modifying Redis if the budget is exhausted.
    """
    total = _get_total_vram_mb()
    r = _client()
    try:
        with r.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(_ALLOC_KEY)
                    raw: dict = pipe.hgetall(_ALLOC_KEY)
                    allocated = sum(int(v) for v in raw.values()) if raw else 0
                    if allocated + vram_mb > total:
                        pipe.reset()
                        return False
                    pipe.multi()
                    pipe.hset(_ALLOC_KEY, job_id, vram_mb)
                    pipe.execute()
                    logger.info(
                        "Allocated %d MB for job %s (used %d/%d MB)",
                        vram_mb, job_id, allocated + vram_mb, total,
                    )
                    return True
                except redis.WatchError:
                    continue
    finally:
        r.close()


def release(job_id: str) -> None:
    """Release the VRAM allocation for a completed (or failed) job."""
    r = _client()
    try:
        removed = r.hdel(_ALLOC_KEY, job_id)
        if removed:
            logger.info("Released VRAM allocation for job %s", job_id)
    finally:
        r.close()


def get_allocations() -> dict[str, int]:
    """Return current allocations as {job_id: vram_mb}."""
    r = _client()
    try:
        raw = r.hgetall(_ALLOC_KEY)
        return {k: int(v) for k, v in raw.items()}
    finally:
        r.close()


def get_allocated_vram_mb() -> int:
    """Return total VRAM currently promised to dispatched jobs."""
    r = _client()
    try:
        raw = r.hvals(_ALLOC_KEY)
        return sum(int(v) for v in raw) if raw else 0
    finally:
        r.close()


def get_total_vram_mb() -> int:
    return _get_total_vram_mb()


def sync_stale_allocations(running_job_ids: set[str]) -> None:
    """Remove allocations for jobs that are no longer active (crash recovery)."""
    r = _client()
    try:
        allocated_ids = set(r.hkeys(_ALLOC_KEY))
        stale = allocated_ids - running_job_ids
        if stale:
            r.hdel(_ALLOC_KEY, *stale)
            logger.warning("Removed stale allocations for jobs: %s", stale)
    finally:
        r.close()
