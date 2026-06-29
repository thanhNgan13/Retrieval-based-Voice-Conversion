from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateMySongUploadUrlRequest(BaseModel):
    file_name: str = Field(
        ...,
        alias="fileName",
        min_length=1,
        max_length=255,
        description="Tên file audio gốc. Dùng để tạo objectPath trên Storage.",
        examples=["my_song.mp3"],
    )
    content_type: str = Field(
        default="audio/mpeg",
        alias="contentType",
        description="MIME type của audio khi PUT lên signed URL. Phải là audio/*.",
        examples=["audio/mpeg", "audio/wav", "audio/flac"],
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Tiêu đề bài hát.",
        examples=["Bài hát của tôi"],
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Mô tả bài hát.",
        examples=["Thu âm tại nhà."],
    )
    artists: Optional[list[str]] = Field(
        default=None,
        description="Danh sách nghệ sĩ. Nếu không truyền sẽ dùng tên user hiện tại.",
        examples=[["Alan Walker"]],
    )
    duration: str = Field(
        default="",
        max_length=20,
        description="Thời lượng bài hát, ví dụ 03:32. Client có thể truyền nếu đã đọc metadata.",
        examples=["03:32"],
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "fileName": "my_song.mp3",
                "contentType": "audio/mpeg",
                "title": "Bài hát của tôi",
                "description": "Thu âm tại nhà.",
                "artists": ["Alan Walker"],
                "duration": "03:32",
            }
        },
    )


class UpdateMySongRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Tiêu đề mới cho bài hát.",
        examples=["Tiêu đề mới"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Mô tả mới cho bài hát.",
        examples=["Mô tả mới."],
    )
    artists: Optional[list[str]] = Field(
        default=None,
        description="Danh sách nghệ sĩ mới.",
        examples=[["Alan Walker"]],
    )
    duration: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Thời lượng mới.",
        examples=["03:32"],
    )
    cover_image: Optional[str] = Field(
        default=None,
        alias="coverImage",
        max_length=2048,
        description="URL ảnh cover mới. Nếu bỏ trống khi upload, server tự tạo URL ảnh theo title.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "title": "Tiêu đề mới",
                "description": "Mô tả mới.",
                "artists": ["Alan Walker"],
                "duration": "03:32",
            }
        },
    )


class ListMySongsQuery(BaseModel):
    limit: Optional[int] = Field(
        default=10,
        ge=1,
        le=100,
        description="Số item mỗi trang, từ 1 đến 100.",
    )
    start_after: Optional[str] = Field(
        default=None,
        alias="startAfter",
        description="Cursor songId của item cuối trang trước.",
    )

    model_config = ConfigDict(populate_by_name=True)
