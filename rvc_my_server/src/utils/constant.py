from src.config.settings import settings

ENV_PREFIX = settings.ENV_PREFIX
API_VERSION = settings.API_VERSION
API_BASE_PATH = f"/{ENV_PREFIX}/{API_VERSION}"

USERS_COLLECTION = "users"
RVC_MODELS_COLLECTION = "rvc_models"

PUBLIC_RVC_MODEL_FOLDER = "public_rvc_model"

DEFAULT_ROLE = "user"
ADMIN_ROLE = "admin"
ADMIN_USER_ID = "admin"


def _parse_expiry_to_seconds(expiry: str) -> int:
    # Accepts "1d", "30d", "12h", "30m", "60s". Numeric only = seconds.
    expiry = expiry.strip().lower()
    if not expiry:
        return 0
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    if expiry[-1] in units:
        return int(expiry[:-1]) * units[expiry[-1]]
    return int(expiry)


ACCESS_TOKEN_TTL_SECONDS = _parse_expiry_to_seconds(settings.ACCESS_TOKEN_EXPIRES_IN)
REFRESH_TOKEN_TTL_SECONDS = _parse_expiry_to_seconds(settings.REFRESH_TOKEN_EXPIRES_IN)
