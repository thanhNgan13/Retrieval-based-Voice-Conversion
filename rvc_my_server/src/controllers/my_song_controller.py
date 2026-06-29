import logging
from typing import Optional

from src.middlewares.auth_middleware import AuthContext
from src.schemas.my_song_schema import CreateMySongUploadUrlRequest, UpdateMySongRequest
from src.services.my_song_service import (
    InvalidMySongRequestError,
    MySongNotFoundError,
    confirm_my_song_upload,
    create_my_song_upload_url,
    delete_my_song,
    get_my_song_detail,
    list_my_songs,
    update_my_song,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class MySongController:
    async def create_upload_url(
        self,
        body: CreateMySongUploadUrlRequest,
        auth: AuthContext,
    ):
        try:
            result = create_my_song_upload_url(body, auth.user_id)
            return send_success_response(201, "Signed upload URL created", result)
        except InvalidMySongRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error creating my song upload URL")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def confirm_upload(self, song_id: str, auth: AuthContext):
        try:
            result = confirm_my_song_upload(auth.user_id, song_id)
            return send_success_response(200, "Song upload confirmed", result)
        except MySongNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except InvalidMySongRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error confirming my song upload")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_songs(
        self,
        limit: Optional[int],
        start_after: Optional[str],
        auth: AuthContext,
    ):
        try:
            result = list_my_songs(auth.user_id, limit, start_after)
            return send_success_response(200, "Songs retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error listing my songs")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def song_detail(self, song_id: str, auth: AuthContext):
        try:
            result = get_my_song_detail(auth.user_id, song_id)
            return send_success_response(200, "Song retrieved successfully", result)
        except MySongNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error getting my song detail")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def update_song(self, song_id: str, body: UpdateMySongRequest, auth: AuthContext):
        try:
            result = update_my_song(auth.user_id, song_id, body)
            return send_success_response(200, "Song updated successfully", result)
        except MySongNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error updating my song")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_song(self, song_id: str, auth: AuthContext):
        try:
            result = delete_my_song(auth.user_id, song_id)
            return send_success_response(200, "Song deleted successfully", result)
        except MySongNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error deleting my song")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


my_song_controller = MySongController()
