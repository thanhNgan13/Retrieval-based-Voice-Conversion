from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.admin_controller import admin_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token_admin
from src.schemas.admin_schema import AdminLoginRequest, AdminRefreshTokenRequest

router = APIRouter()


@router.post(
    "/login",
    summary="Admin login (username + password)",
    description="Đăng nhập admin. Trả về accessToken/refreshToken được ký bằng ADMIN_JWT_SECRET.",
)
async def login(body: AdminLoginRequest):
    return await admin_controller.login(body)


@router.post(
    "/refresh",
    summary="Exchange an admin refresh token for a new access token",
)
async def refresh(body: AdminRefreshTokenRequest):
    return await admin_controller.refresh(body)


@router.get(
    "/users",
    summary="List all users in the system (cursor pagination)",
)
async def list_users(
    limit: Optional[int] = Query(default=10, ge=1, le=100, description="Số item/trang (1–100)."),
    startAfter: Optional[str] = Query(default=None, description="userId làm cursor trang kế."),
    _: AuthContext = Depends(authenticate_token_admin),
):
    return await admin_controller.list_users(limit=limit, start_after=startAfter)
