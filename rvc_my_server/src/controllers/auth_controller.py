import logging

from src.schemas.auth_schema import LoginRequest, RefreshTokenRequest, RegisterRequest
from src.services.auth_service import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserNotFoundError,
    login_user,
    refresh_access_token,
    register_user,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class AuthController:
    async def register(self, body: RegisterRequest):
        try:
            result = register_user(
                email=str(body.email),
                password=body.password,
                name=body.name,
            )
            return send_success_response(201, "User created successfully", result)
        except EmailAlreadyExistsError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in register")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def login(self, body: LoginRequest):
        try:
            result = login_user(email=str(body.email), password=body.password)
            return send_success_response(200, "Login successful", result)
        except InvalidCredentialsError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in login")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def refresh(self, body: RefreshTokenRequest):
        try:
            result = refresh_access_token(body.refreshToken)
            return send_success_response(200, "Token refreshed", result)
        except InvalidRefreshTokenError as exc:
            return send_error_response(403, "Invalid Token", str(exc) or "Refresh token invalid or expired")
        except UserNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in refresh")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


auth_controller = AuthController()
