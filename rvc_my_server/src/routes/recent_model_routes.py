from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.recent_model_controller import recent_model_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token
from src.schemas.recent_model_schema import AddRecentModelRequest

router = APIRouter()


@router.post("", summary="Save a model to current user's recent models")
async def add_recent_model(
    body: AddRecentModelRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await recent_model_controller.add(auth, body)


@router.get("", summary="List current user's recent models (cursor pagination)")
async def list_recent_models(
    limit: Optional[int] = Query(default=10, ge=1, le=100),
    startAfter: Optional[str] = Query(default=None, description="rvcModelId của item cuối trang trước"),
    auth: AuthContext = Depends(authenticate_token),
):
    return await recent_model_controller.list_models(auth, limit, startAfter)
