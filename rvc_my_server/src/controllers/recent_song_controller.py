import logging
from typing import Optional

from src.middlewares.auth_middleware import AuthContext
from src.schemas.recent_song_schema import AddRecentSongRequest
from src.services.recent_song_service import (
    SongNotFoundError,
    add_recent_song,
    list_recent_songs,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class RecentSongController:
    async def add(self, auth: AuthContext, body: AddRecentSongRequest):
        try:
            result = add_recent_song(auth.user_id, body.songId, body.playlistId)
            return send_success_response(200, "Recent song saved", result)
        except SongNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in add_recent_song")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_songs(
        self, auth: AuthContext, limit: Optional[int], start_after: Optional[str]
    ):
        try:
            result = list_recent_songs(auth.user_id, limit, start_after)
            return send_success_response(200, "Recent songs retrieved", result)
        except Exception as exc:
            logger.exception("Error in list_recent_songs")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


recent_song_controller = RecentSongController()
