import logging
from typing import Optional

from src.middlewares.auth_middleware import AuthContext
from src.schemas.recent_model_schema import AddRecentModelRequest
from src.services.recent_model_service import (
    RvcModelNotFoundError,
    add_recent_model,
    list_recent_models,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class RecentModelController:
    async def add(self, auth: AuthContext, body: AddRecentModelRequest):
        try:
            result = add_recent_model(auth.user_id, body.rvcModelId)
            return send_success_response(200, "Recent model saved", result)
        except RvcModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in add_recent_model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_models(
        self, auth: AuthContext, limit: Optional[int], start_after: Optional[str]
    ):
        try:
            result = list_recent_models(auth.user_id, limit, start_after)
            return send_success_response(200, "Recent models retrieved", result)
        except Exception as exc:
            logger.exception("Error in list_recent_models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


recent_model_controller = RecentModelController()
