"""Routes for user's personal song library (my_songs subcollection).

Upload flow:
  1. POST /my-song-services/upload-url  → nhận signedUrl + songId
  2. PUT <signedUrl> với binary audio    → upload thẳng lên Firebase Storage
  3. POST /my-song-services/songs/{songId}/confirm → xác nhận upload thành công
  4. GET  /my-song-services/songs         → danh sách bài hát (có audioUrl tạm thời)
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.my_song_controller import my_song_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token
from src.schemas.my_song_schema import CreateMySongUploadUrlRequest, UpdateMySongRequest

router = APIRouter()


@router.post(
    "/upload-url",
    summary="Tạo signed PUT URL để upload bài hát",
    description=(
        "Trả về một signed PUT URL để client upload trực tiếp audio lên Firebase Storage. "
        "Đồng thời tạo bản ghi Firestore với `status=pending`. "
        "Sau khi PUT thành công, gọi `POST /songs/{songId}/confirm` để kích hoạt bài hát.\n\n"
        "**Trình tự**\n"
        "1. `POST /my-song-services/upload-url` → nhận `songId` + `uploadUrl`\n"
        "2. `PUT <uploadUrl>` với header `Content-Type` tương ứng và binary audio\n"
        "3. `POST /my-song-services/songs/{songId}/confirm`"
    ),
)
async def create_upload_url(
    body: CreateMySongUploadUrlRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.create_upload_url(body, auth)


@router.post(
    "/songs/{song_id}/confirm",
    summary="Xác nhận đã upload audio thành công",
    description=(
        "Kiểm tra file tồn tại trên Firebase Storage rồi cập nhật `status=uploaded`. "
        "Trả về thông tin bài hát kèm `audioUrl` (signed GET URL tạm thời để phát nhạc)."
    ),
)
async def confirm_upload(
    song_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.confirm_upload(song_id, auth)


@router.get(
    "/songs",
    summary="Danh sách bài hát của user (có phân trang)",
    description=(
        "Trả danh sách bài hát thuộc `users/{userId}/my_songs`, sắp xếp mới nhất trước. "
        "Mỗi bài hát đã `status=uploaded` có `audioUrl` là signed GET URL tạm thời. "
        "URL hết hạn theo `SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS`."
    ),
)
async def list_songs(
    limit: Optional[int] = Query(default=10, ge=1, le=100, description="Số item mỗi trang."),
    startAfter: Optional[str] = Query(default=None, description="Cursor songId của item cuối trang trước."),
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.list_songs(limit, startAfter, auth)


@router.get(
    "/songs/{song_id}",
    summary="Chi tiết một bài hát",
    description="Trả thông tin bài hát và `audioUrl` (signed GET URL) nếu đã upload.",
)
async def song_detail(
    song_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.song_detail(song_id, auth)


@router.patch(
    "/songs/{song_id}",
    summary="Cập nhật metadata bài hát (title, description)",
    description="Chỉ cập nhật các trường được cung cấp. File audio không thay đổi.",
)
async def update_song(
    song_id: str,
    body: UpdateMySongRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.update_song(song_id, body, auth)


@router.delete(
    "/songs/{song_id}",
    summary="Xoá bài hát",
    description=(
        "Xoá bản ghi Firestore và file audio trên Firebase Storage. "
        "Nếu file Storage không tồn tại, vẫn xoá Firestore và trả về thành công."
    ),
)
async def delete_song(
    song_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await my_song_controller.delete_song(song_id, auth)
