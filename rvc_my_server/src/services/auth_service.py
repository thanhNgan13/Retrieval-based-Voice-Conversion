import bcrypt

from src.middlewares.auth_middleware import (
    generate_access_token,
    generate_refresh_token,
    verify_refresh_token,
)
from src.models.user_model import (
    add_user_to_firestore,
    get_user_by_email,
    get_user_by_id,
    prepare_user_data,
)
from src.utils.constant import (
    ACCESS_TOKEN_TTL_SECONDS,
    DEFAULT_ROLE,
    REFRESH_TOKEN_TTL_SECONDS,
)
from src.utils.data_transform import convert_firestore_doc
from src.utils.id_generator import generate_user_id


class EmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


_PUBLIC_DROP_KEYS = ("password_hash",)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _public_user(doc: dict) -> dict:
    return convert_firestore_doc(doc, drop_keys=_PUBLIC_DROP_KEYS)


def _build_token_bundle(user_id: str, role: str) -> dict:
    return {
        "accessToken": generate_access_token(user_id, role),
        "refreshToken": generate_refresh_token(user_id, role),
        "accessTokenExpiresIn": ACCESS_TOKEN_TTL_SECONDS,
        "refreshTokenExpiresIn": REFRESH_TOKEN_TTL_SECONDS,
    }


def register_user(email: str, password: str, name: str) -> dict:
    existing = get_user_by_email(email)
    if existing is not None:
        raise EmailAlreadyExistsError("Email already registered")

    user_id = generate_user_id()
    user_data = prepare_user_data(
        user_id=user_id,
        email=email,
        name=name,
        password_hash=_hash_password(password),
        role=DEFAULT_ROLE,
    )
    add_user_to_firestore(user_data)

    return {
        "user": _public_user(user_data),
        **_build_token_bundle(user_id, DEFAULT_ROLE),
    }


def login_user(email: str, password: str) -> dict:
    doc = get_user_by_email(email)
    if not doc:
        raise InvalidCredentialsError("Email or password is incorrect")
    if not _verify_password(password, doc.get("password_hash", "")):
        raise InvalidCredentialsError("Email or password is incorrect")

    return {
        "user": _public_user(doc),
        **_build_token_bundle(doc["user_id"], doc.get("role", DEFAULT_ROLE)),
    }


def refresh_access_token(refresh_token: str) -> dict:
    try:
        payload = verify_refresh_token(refresh_token, is_admin=False)
    except Exception as exc:
        raise InvalidRefreshTokenError(str(exc)) from exc

    user_id = payload.get("userId")
    if not user_id:
        raise InvalidRefreshTokenError("Invalid refresh token payload")

    doc = get_user_by_id(user_id)
    if not doc:
        raise UserNotFoundError("User not found")

    return _build_token_bundle(user_id, doc.get("role", DEFAULT_ROLE))
