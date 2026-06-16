from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV_PREFIX: str = "dev"
    API_VERSION: str = "v1"
    PORT: int = 8000

    JWT_SECRET: str = "change_me_jwt_secret"
    REFRESH_TOKEN_SECRET: str = "change_me_refresh_secret"
    ADMIN_JWT_SECRET: str = "change_me_admin_secret"
    ADMIN_REFRESH_TOKEN_SECRET: str = "change_me_admin_refresh_secret"
    ACCESS_TOKEN_EXPIRES_IN: str = "1d"
    REFRESH_TOKEN_EXPIRES_IN: str = "30d"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_STORAGE_BUCKET: str = ""

    # Folder holding hubert_base.pt, rmvpe.pt, ... (downloaded via admin setup-assets).
    ASSETS_DIR: str = "./assets"
    # Local cache for downloaded model/.index files (per rvcModelId) and infer outputs.
    INFER_CACHE_DIR: str = "./cache"

    # Redis/Celery for long-running RVC training jobs + realtime progress events.
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # Local workspace for Celery training jobs.
    TRAIN_CACHE_DIR: str = "./cache/train_jobs"

    # Signed URL expiry for direct upload/download.
    SIGNED_UPLOAD_URL_EXPIRES_SECONDS: int = 3600
    SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS: int = 3600

    # Resource-aware job scheduler.
    # VRAM budget (MB) per job type — tune to match your GPU capacity.
    TRAIN_JOB_VRAM_MB: int = 4096
    INFER_JOB_VRAM_MB: int = 3072
    # Used as total budget when CUDA is not available (CPU-only or test env).
    FALLBACK_TOTAL_VRAM_MB: int = 8192
    # How often the scheduler polls for queued jobs (seconds).
    SCHEDULER_INTERVAL_SECONDS: float = 3.0
    # Celery worker thread pool size — must be >= max expected concurrent jobs.
    CELERY_WORKER_CONCURRENCY: int = 4


settings = Settings()
