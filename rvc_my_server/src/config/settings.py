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


settings = Settings()
