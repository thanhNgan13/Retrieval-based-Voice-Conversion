from fastapi import APIRouter, Depends

from src.controllers.user_controller import user_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token

router = APIRouter()


@router.get(
    "/profile",
    summary="Get current user's profile",
)
async def get_profile(auth: AuthContext = Depends(authenticate_token)):
    return await user_controller.get_profile(auth)
