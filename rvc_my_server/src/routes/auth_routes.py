from fastapi import APIRouter

from src.controllers.auth_controller import auth_controller
from src.schemas.auth_schema import LoginRequest, RefreshTokenRequest, RegisterRequest

router = APIRouter()


@router.post(
    "/register",
    summary="Register a new user",
    description="Create a new user account with email and password.",
)
async def register(body: RegisterRequest):
    return await auth_controller.register(body)


@router.post(
    "/login",
    summary="Login with email and password",
)
async def login(body: LoginRequest):
    return await auth_controller.login(body)


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token",
)
async def refresh(body: RefreshTokenRequest):
    return await auth_controller.refresh(body)
