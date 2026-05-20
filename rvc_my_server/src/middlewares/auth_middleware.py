from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.settings import settings
from src.utils.constant import (
    ACCESS_TOKEN_TTL_SECONDS,
    ADMIN_ROLE,
    REFRESH_TOKEN_TTL_SECONDS,
)


JWT_ALGORITHM = "HS256"

# Two distinct schemes so Swagger's Authorize popup shows separate input boxes:
#   - bearerAuth      → user token  (POST /auth-services/login)
#   - bearerAdminAuth → admin token (POST /admin-services/login)
# Each token is signed with a DIFFERENT secret (JWT_SECRET vs ADMIN_JWT_SECRET),
# so pasting one into the other's box will return 403 from the matching middleware.
# auto_error=False: tự xử lý "thiếu token" để trả đúng response envelope của dự án.
bearer_user_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    description="JWT access token của USER (lấy từ POST /auth-services/login).",
    auto_error=False,
)
bearer_admin_scheme = HTTPBearer(
    scheme_name="bearerAdminAuth",
    description=(
        "JWT access token của ADMIN (lấy từ POST /admin-services/login). "
        "Ký bằng ADMIN_JWT_SECRET, khác với token user."
    ),
    auto_error=False,
)


class AuthContext:
    def __init__(self, user_id: str, payload: dict, is_admin: bool = False) -> None:
        self.user_id = user_id
        self.user = payload
        self.is_admin = is_admin


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_access_token(user_id: str, role: str = "user") -> str:
    payload = {
        "userId": user_id,
        "role": role,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).timestamp()),
    }
    secret = settings.ADMIN_JWT_SECRET if role == ADMIN_ROLE else settings.JWT_SECRET
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def generate_refresh_token(user_id: str, role: str = "user") -> str:
    payload = {
        "userId": user_id,
        "role": role,
        "type": "refresh",
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)).timestamp()),
    }
    secret = (
        settings.ADMIN_REFRESH_TOKEN_SECRET
        if role == ADMIN_ROLE
        else settings.REFRESH_TOKEN_SECRET
    )
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def build_token_bundle(user_id: str, role: str = "user") -> dict:
    return {
        "accessToken": generate_access_token(user_id, role),
        "refreshToken": generate_refresh_token(user_id, role),
        "accessTokenExpiresIn": ACCESS_TOKEN_TTL_SECONDS,
        "refreshTokenExpiresIn": REFRESH_TOKEN_TTL_SECONDS,
    }


def _decode(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])


def verify_refresh_token(token: str, is_admin: bool = False) -> dict:
    secret = (
        settings.ADMIN_REFRESH_TOKEN_SECRET if is_admin else settings.REFRESH_TOKEN_SECRET
    )
    payload = _decode(token, secret)
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return payload


def _require_credentials(creds: Optional[HTTPAuthorizationCredentials]) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Access Denied", "message": "Access Token Required"},
        )
    return creds.credentials


def _verify(token: str, secret: str) -> dict:
    try:
        return _decode(token, secret)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid Token", "message": "Access Token Invalid Or Expired"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid Token", "message": "Access Token Invalid Or Expired"},
        )


def authenticate_token(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_user_scheme),
) -> AuthContext:
    token = _require_credentials(creds)
    payload = _verify(token, settings.JWT_SECRET)
    user_id = payload.get("userId")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid Token", "message": "Access Token Invalid Or Expired"},
        )
    return AuthContext(user_id=user_id, payload=payload, is_admin=False)


def verify_user_access_token(token: str) -> AuthContext:
    payload = _verify(token, settings.JWT_SECRET)
    user_id = payload.get("userId")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid Token", "message": "Access Token Invalid Or Expired"},
        )
    return AuthContext(user_id=user_id, payload=payload, is_admin=False)


def authenticate_token_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_admin_scheme),
) -> AuthContext:
    token = _require_credentials(creds)
    payload = _verify(token, settings.ADMIN_JWT_SECRET)
    user_id = payload.get("userId")
    if not user_id or payload.get("role") != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid Token", "message": "Access Token Invalid Or Expired"},
        )
    return AuthContext(user_id=user_id, payload=payload, is_admin=True)


def authenticate_user_or_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_user_scheme),
) -> AuthContext:
    token = _require_credentials(creds)
    try:
        payload = _decode(token, settings.ADMIN_JWT_SECRET)
        if payload.get("role") == ADMIN_ROLE:
            return AuthContext(user_id=payload["userId"], payload=payload, is_admin=True)
    except jwt.InvalidTokenError:
        pass
    payload = _verify(token, settings.JWT_SECRET)
    return AuthContext(user_id=payload["userId"], payload=payload, is_admin=False)
