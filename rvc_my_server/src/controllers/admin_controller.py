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
from src.services.asset_service import (
    get_assets_status,
    get_mdxnet_assets_status,
    get_training_assets_status,
    get_uvr5_assets_status,
    setup_default_assets,
    setup_mdxnet_assets,
    setup_training_assets,
    setup_uvr5_assets,
)
from src.services.system_service import get_torch_status
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

    async def setup_assets(self, force: bool):
        try:
            result = setup_default_assets(force=force)
            message = (
                "Default infer assets are ready"
                if result["ready"]
                else "Some assets failed to download"
            )
            status_code = 200 if result["ready"] else 500
            if result["ready"]:
                return send_success_response(status_code, message, result)
            return send_error_response(status_code, "ASSET_SETUP_FAILED", message)
        except Exception as exc:
            logger.exception("Error in admin setup_assets")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def get_assets_status(self):
        try:
            result = get_assets_status()
            return send_success_response(200, "Assets status retrieved", result)
        except Exception as exc:
            logger.exception("Error in admin get_assets_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def setup_uvr5_assets(self, force: bool):
        try:
            result = setup_uvr5_assets(force=force)
            message = (
                "UVR5 assets are ready"
                if result["ready"]
                else "Some UVR5 assets failed to download"
            )
            status_code = 200 if result["ready"] else 500
            if result["ready"]:
                return send_success_response(status_code, message, result)
            return send_error_response(status_code, "UVR5_ASSET_SETUP_FAILED", message)
        except Exception as exc:
            logger.exception("Error in admin setup_uvr5_assets")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def get_uvr5_assets_status(self):
        try:
            result = get_uvr5_assets_status()
            return send_success_response(200, "UVR5 assets status retrieved", result)
        except Exception as exc:
            logger.exception("Error in admin get_uvr5_assets_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def setup_mdxnet_assets(self, force: bool):
        try:
            result = setup_mdxnet_assets(force=force)
            message = (
                "MDX-Net assets are ready"
                if result["ready"]
                else "Some MDX-Net assets failed to download"
            )
            status_code = 200 if result["ready"] else 500
            if result["ready"]:
                return send_success_response(status_code, message, result)
            return send_error_response(status_code, "MDXNET_ASSET_SETUP_FAILED", message)
        except Exception as exc:
            logger.exception("Error in admin setup_mdxnet_assets")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def get_mdxnet_assets_status(self):
        try:
            result = get_mdxnet_assets_status()
            return send_success_response(200, "MDX-Net assets status retrieved", result)
        except Exception as exc:
            logger.exception("Error in admin get_mdxnet_assets_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def get_training_assets_status(self):
        try:
            result = get_training_assets_status()
            return send_success_response(
                200,
                "Training assets status retrieved",
                result,
            )
        except Exception as exc:
            logger.exception("Error in admin get_training_assets_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def setup_training_assets(self, force: bool):
        try:
            result = setup_training_assets(force=force)
            if result["ready"]:
                return send_success_response(200, "Training assets are ready", result)

            pretrained_failed = any(
                item.get("status") == "failed"
                for item in result.get("pretrainedSetup", [])
            )
            infer_failed = not result.get("inferSetup", {}).get("ready", False)
            mute_requires_copy = (
                result.get("muteSetup", {}).get("status")
                == "missing_manual_copy_required"
            )
            if mute_requires_copy and not (pretrained_failed or infer_failed):
                return send_success_response(
                    200,
                    "Training assets downloaded; logs/mute requires manual copy",
                    result,
                )

            return send_error_response(
                500,
                "TRAINING_ASSET_SETUP_FAILED",
                "Some training assets failed to install",
            )
        except Exception as exc:
            logger.exception("Error in admin setup_training_assets")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def torch_status(self):
        try:
            result = get_torch_status()
            return send_success_response(200, "Torch status retrieved", result)
        except Exception as exc:
            logger.exception("Error in admin torch_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


admin_controller = AdminController()
