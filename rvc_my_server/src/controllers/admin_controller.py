import logging
from typing import Optional

from src.schemas.admin_schema import AdminLoginRequest, AdminRefreshTokenRequest
from src.services.admin_service import (
    InvalidAdminCredentialsError,
    InvalidAdminRefreshTokenError,
    admin_login,
    admin_refresh_access_token,
    list_all_users,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class AdminController:
    async def login(self, body: AdminLoginRequest):
        try:
            result = admin_login(username=body.username, password=body.password)
            return send_success_response(200, "Admin login successful", result)
        except InvalidAdminCredentialsError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in admin login")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def refresh(self, body: AdminRefreshTokenRequest):
        try:
            result = admin_refresh_access_token(body.refreshToken)
            return send_success_response(200, "Admin token refreshed", result)
        except InvalidAdminRefreshTokenError as exc:
            return send_error_response(
                403, "Invalid Token", str(exc) or "Refresh token invalid or expired"
            )
        except Exception as exc:
            logger.exception("Error in admin refresh")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_users(self, limit: Optional[int], start_after: Optional[str]):
        try:
            result = list_all_users(limit=limit, start_after=start_after)
            return send_success_response(200, "Users retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error in admin list_users")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


admin_controller = AdminController()
