"""Resource-aware job scheduler.

Runs as an asyncio background task inside the FastAPI process.  On every tick it:
  1. Syncs stale Redis allocations (crash recovery — jobs that died without releasing).
  2. Fetches all status="queued" jobs from Firestore (train + infer).
  3. Tries to allocate VRAM for each job in FIFO order.
  4. Dispatches eligible jobs to Celery via send_task().

When a Celery task finishes it publishes a message on the Redis channel
`scheduler:trigger`; the scheduler also subscribes to that channel so it wakes
up immediately instead of waiting for the next polling interval.
"""
import asyncio
import logging

import redis.asyncio as aioredis

from src.config.settings import settings

logger = logging.getLogger(__name__)


class JobScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="job_scheduler")
        logger.info("JobScheduler started (interval=%.1fs)", settings.SCHEDULER_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("JobScheduler stopped")

    # ------------------------------------------------------------------
    # Main loop — periodic tick + Redis pub/sub trigger
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("scheduler:trigger")

        trigger_task = asyncio.create_task(self._listen_triggers(pubsub))
        try:
            while True:
                await self._tick()
                await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            trigger_task.cancel()
            try:
                await trigger_task
            except asyncio.CancelledError:
                pass
            await pubsub.unsubscribe("scheduler:trigger")
            await redis_client.aclose()
            raise

    async def _listen_triggers(self, pubsub) -> None:
        """Wake up the scheduler immediately when a job finishes."""
        async for msg in pubsub.listen():
            if msg and msg.get("type") == "message":
                await self._tick()

    # ------------------------------------------------------------------
    # Dispatch logic (runs in a thread pool to avoid blocking the event loop)
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        try:
            await asyncio.get_event_loop().run_in_executor(None, _dispatch_queued_jobs)
        except Exception:
            logger.exception("JobScheduler tick error")


# ------------------------------------------------------------------
# Scheduler singleton
# ------------------------------------------------------------------

job_scheduler = JobScheduler()


# ------------------------------------------------------------------
# Sync dispatch logic (runs in ThreadPoolExecutor)
# ------------------------------------------------------------------

def _dispatch_queued_jobs() -> None:
    from src.config.firebase import get_db
    from src.services import resource_manager
    from src.utils.constant import RVC_SONG_INFER_JOBS_COLLECTION, RVC_TRAIN_JOBS_COLLECTION

    db = get_db()

    # --- 1. Sync stale allocations (crash recovery) ---
    train_running = {
        d.to_dict()["train_job_id"]
        for d in db.collection(RVC_TRAIN_JOBS_COLLECTION)
                   .where("status", "in", ["queued", "running"])
                   .stream()
    }
    infer_running = {
        d.to_dict()["song_infer_job_id"]
        for d in db.collection(RVC_SONG_INFER_JOBS_COLLECTION)
                   .where("status", "in", ["queued", "running"])
                   .stream()
    }
    resource_manager.sync_stale_allocations(train_running | infer_running)

    # --- 2. Fetch queued jobs from both collections ---
    # No order_by here — sorting is done in Python after merging, so no
    # composite index is needed (Firestore auto-indexes single fields).
    train_queued = [
        d.to_dict()
        for d in db.collection(RVC_TRAIN_JOBS_COLLECTION)
                   .where("status", "==", "queued")
                   .stream()
    ]
    infer_queued = [
        d.to_dict()
        for d in db.collection(RVC_SONG_INFER_JOBS_COLLECTION)
                   .where("status", "==", "queued")
                   .stream()
    ]

    # --- 3. Merge and sort FIFO across both types ---
    all_queued: list[tuple[str, dict]] = sorted(
        [("train", d) for d in train_queued] + [("infer", d) for d in infer_queued],
        key=lambda x: x[1].get("created_at", ""),
    )

    if not all_queued:
        return

    # Jobs already allocated in Redis (dispatched but not yet picked up by worker)
    already_allocated = set(resource_manager.get_allocations().keys())

    for job_type, doc in all_queued:
        job_id = doc["train_job_id"] if job_type == "train" else doc["song_infer_job_id"]
        vram_mb = (
            settings.TRAIN_JOB_VRAM_MB if job_type == "train"
            else settings.INFER_JOB_VRAM_MB
        )

        if job_id in already_allocated:
            # Already dispatched — waiting for worker to pick it up
            continue

        if resource_manager.try_allocate(job_id, vram_mb):
            _dispatch_to_celery(job_type, job_id)
        else:
            logger.debug(
                "Not enough VRAM for %s job %s (needs %d MB) — queued",
                job_type, job_id, vram_mb,
            )


def _dispatch_to_celery(job_type: str, job_id: str) -> None:
    from src.config.celery_app import celery_app

    task_name = "train_rvc_model" if job_type == "train" else "infer_song_cover"
    celery_app.send_task(task_name, args=[job_id])
    logger.info("Dispatched %s job %s to Celery (task=%s)", job_type, job_id, task_name)


def trigger_scheduler() -> None:
    """Call from Celery worker (sync) to wake the scheduler after a job finishes."""
    import redis as sync_redis

    r = sync_redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        r.publish("scheduler:trigger", "1")
    except Exception:
        logger.warning("Could not publish scheduler trigger")
    finally:
        r.close()
