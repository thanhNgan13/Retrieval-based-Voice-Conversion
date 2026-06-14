import logging

from fastapi import UploadFile

from src.middlewares.auth_middleware import AuthContext
from src.services.separation_service import (
    InvalidSeparationRequestError,
    SeparationRuntimeError,
    list_mdx_models,
    separate_song,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class SeparationController:
    async def models(self):
        try:
            result = list_mdx_models()
            return send_success_response(200, "MDX-Net models retrieved", result)
        except Exception as exc:
            logger.exception("Error in list MDX-Net models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def separate(
        self,
        audio_file: UploadFile,
        keep_local: bool,
        auth: AuthContext,
    ):
        try:
            result = separate_song(
                audio_file=audio_file,
                user_id=auth.user_id,
                keep_local=keep_local,
            )
            return send_success_response(200, "Audio separation successful", result)
        except InvalidSeparationRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except SeparationRuntimeError as exc:
            return send_error_response(500, "SEPARATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in audio separation")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


separation_controller = SeparationController()
