import logging
from typing import Optional

from fastapi import UploadFile

from src.middlewares.auth_middleware import AuthContext
from src.schemas.user_model_schema import UpdateUserModelRequest
from src.services.user_model_service import (
    InvalidUserModelUploadError,
    UserModelNotFoundError,
    delete_user_model,
    get_user_model_detail,
    list_user_models,
    update_user_model,
    upload_user_model,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class UserModelController:
    async def upload(
        self,
        title: str,
        description: str,
        model_file: UploadFile,
        index_file: UploadFile,
        thumbnail: Optional[UploadFile],
        auth: AuthContext,
    ):
        try:
            result = upload_user_model(
                title=title,
                description=description,
                model_file=model_file,
                index_file=index_file,
                thumbnail_file=thumbnail,
                user_id=auth.user_id,
            )
            return send_success_response(201, "User model uploaded successfully", result)
        except InvalidUserModelUploadError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error uploading user model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list(self, user_id: str, limit: Optional[int], start_after: Optional[str]):
        try:
            result = list_user_models(user_id=user_id, limit=limit, start_after=start_after)
            return send_success_response(200, "User models retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error listing user models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def detail(self, user_id: str, rvc_model_id: str):
        try:
            result = get_user_model_detail(user_id=user_id, rvc_model_id=rvc_model_id)
            return send_success_response(200, "User model retrieved successfully", result)
        except UserModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error getting user model detail")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def update(self, rvc_model_id: str, body: UpdateUserModelRequest, auth: AuthContext):
        try:
            result = update_user_model(
                user_id=auth.user_id,
                rvc_model_id=rvc_model_id,
                title=body.title,
                description=body.description,
            )
            return send_success_response(200, "User model updated successfully", result)
        except UserModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error updating user model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_one(self, rvc_model_id: str, auth: AuthContext):
        try:
            delete_user_model(user_id=auth.user_id, rvc_model_id=rvc_model_id)
            return send_success_response(200, "User model deleted successfully")
        except UserModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error deleting user model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


user_model_controller = UserModelController()
