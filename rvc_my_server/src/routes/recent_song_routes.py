from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.recent_song_controller import recent_song_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token
from src.schemas.recent_song_schema import AddRecentSongRequest

router = APIRouter()


@router.post("", summary="Save a song to current user's recent songs")
async def add_recent_song(
    body: AddRecentSongRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await recent_song_controller.add(auth, body)


@router.get("", summary="List current user's recent songs (cursor pagination)")
async def list_recent_songs(
    limit: Optional[int] = Query(default=10, ge=1, le=100),
    startAfter: Optional[str] = Query(default=None, description="songId của item cuối trang trước"),
    auth: AuthContext = Depends(authenticate_token),
):
    return await recent_song_controller.list_songs(auth, limit, startAfter)
