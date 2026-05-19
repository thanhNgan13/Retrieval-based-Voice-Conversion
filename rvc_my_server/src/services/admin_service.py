from typing import Optional

from src.config.settings import settings
from src.middlewares.auth_middleware import build_token_bundle, verify_refresh_token
from src.models.user_model import list_users_paginated
from src.utils.constant import ADMIN_ROLE, ADMIN_USER_ID
from src.utils.cursor_pagination import normalize_limit
from src.utils.data_transform import convert_firestore_doc


class InvalidAdminCredentialsError(Exception):
    pass


class InvalidAdminRefreshTokenError(Exception):
    pass


_USER_DROP_KEYS = ("password_hash",)


def _admin_identity() -> dict:
    return {
        "userId": ADMIN_USER_ID,
        "username": settings.ADMIN_USERNAME,
        "role": ADMIN_ROLE,
    }


def admin_login(username: str, password: str) -> dict:
    if username != settings.ADMIN_USERNAME or password != settings.ADMIN_PASSWORD:
        raise InvalidAdminCredentialsError("Username or password is incorrect")
    return {
        "user": _admin_identity(),
        "tokens": build_token_bundle(ADMIN_USER_ID, ADMIN_ROLE),
    }


def admin_refresh_access_token(refresh_token: str) -> dict:
    try:
        payload = verify_refresh_token(refresh_token, is_admin=True)
    except Exception as exc:
        raise InvalidAdminRefreshTokenError(str(exc)) from exc

    if payload.get("role") != ADMIN_ROLE or payload.get("userId") != ADMIN_USER_ID:
        raise InvalidAdminRefreshTokenError("Not a valid admin refresh token")

    return {"tokens": build_token_bundle(ADMIN_USER_ID, ADMIN_ROLE)}


def list_all_users(limit: Optional[int], start_after: Optional[str]) -> dict:
    n = normalize_limit(limit)
    items, has_next = list_users_paginated(n, start_after)
    paginated_items = [convert_firestore_doc(d, drop_keys=_USER_DROP_KEYS) for d in items]
    next_cursor = items[-1].get("user_id") if has_next and items else None
    return {
        "paginatedItems": paginated_items,
        "pagination": {
            "limit": n,
            "hasNext": has_next,
            "nextCursor": next_cursor,
            "currentCount": len(paginated_items),
        },
    }
