import logging
from typing import Optional

from fastapi import UploadFile

from src.middlewares.auth_middleware import AuthContext
from src.schemas.rvc_model_schema import DeleteRvcModelsRequest, UpdateRvcModelRequest
from src.services.rvc_model_service import (
    InvalidUploadError,
    RvcModelNotFoundError,
    delete_all_rvc_models,
    delete_rvc_model,
    delete_rvc_models_by_ids,
    get_rvc_model_detail,
    list_rvc_models,
    update_rvc_model,
    upload_rvc_model,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class RvcModelController:
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
            result = upload_rvc_model(
                title=title,
                description=description,
                model_file=model_file,
                index_file=index_file,
                thumbnail_file=thumbnail,
                created_by=auth.user_id,
            )
            return send_success_response(201, "RVC model uploaded successfully", result)
        except InvalidUploadError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in upload rvc model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list(self, limit: Optional[int], start_after: Optional[str]):
        try:
            result = list_rvc_models(limit=limit, start_after=start_after)
            return send_success_response(200, "RVC models retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error in list rvc models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def detail(self, rvc_model_id: str):
        try:
            if not rvc_model_id:
                return send_error_response(400, "VALIDATION_FAILED", "rvcModelId is required")
            result = get_rvc_model_detail(rvc_model_id)
            return send_success_response(200, "RVC model retrieved successfully", result)
        except RvcModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in get rvc model detail")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def update(
        self,
        rvc_model_id: str,
        body: UpdateRvcModelRequest,
        auth: AuthContext,
    ):
        try:
            result = update_rvc_model(
                rvc_model_id=rvc_model_id,
                title=body.title,
                description=body.description,
            )
            return send_success_response(200, "RVC model updated successfully", result)
        except RvcModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in update rvc model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_one(self, rvc_model_id: str, auth: AuthContext):
        try:
            delete_rvc_model(rvc_model_id)
            return send_success_response(200, "RVC model deleted successfully")
        except RvcModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in delete rvc model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_many(self, body: DeleteRvcModelsRequest, auth: AuthContext):
        try:
            result = delete_rvc_models_by_ids(body.rvc_model_ids)
            return send_success_response(200, "RVC models deleted successfully", result)
        except Exception as exc:
            logger.exception("Error in delete rvc models by ids")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_all(self, auth: AuthContext):
        try:
            count = delete_all_rvc_models()
            return send_success_response(
                200,
                "All RVC models deleted successfully",
                {"deletedCount": count},
            )
        except Exception as exc:
            logger.exception("Error in delete all rvc models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


rvc_model_controller = RvcModelController()
