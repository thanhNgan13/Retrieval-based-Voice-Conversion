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

    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_STORAGE_BUCKET: str = ""


settings = Settings()
