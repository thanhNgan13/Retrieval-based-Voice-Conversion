import logging

from src.middlewares.auth_middleware import AuthContext
from src.services.user_service import UserNotFoundError, get_my_profile
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class UserController:
    async def get_profile(self, auth: AuthContext):
        try:
            user = get_my_profile(auth.user_id)
            return send_success_response(200, "User information", user)
        except UserNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in get_profile")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


user_controller = UserController()
