from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from src.controllers.user_model_controller import user_model_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token
from src.schemas.user_model_schema import UpdateUserModelRequest

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload model .pth + .index vào collection cá nhân của user",
    description=(
        "Upload file model trực tiếp (không cần training) vào collection `rvc_models` "
        "của user. File sẽ được lưu tại "
        "`user_rvc_model/{userId}/{rvcModelId}_{titleSlug}/model.pth` và `model.index`."
    ),
)
async def upload(
    title: str = Form(..., min_length=1, max_length=120, examples=["Giọng tôi"]),
    description: str = Form("", max_length=2000, examples=["Model giọng nói cá nhân."]),
    modelFile: UploadFile = File(..., description="File trọng số .pth của RVC model"),
    indexFile: UploadFile = File(..., description="File .index FAISS của RVC model"),
    thumbnail: Optional[UploadFile] = File(default=None, description="Ảnh thumbnail (jpg/jpeg/png/webp). Tuỳ chọn."),
    auth: AuthContext = Depends(authenticate_token),
):
    return await user_model_controller.upload(
        title=title,
        description=description,
        model_file=modelFile,
        index_file=indexFile,
        thumbnail=thumbnail,
        auth=auth,
    )


@router.get(
    "/models",
    summary="Lấy danh sách model cá nhân của user (cursor pagination)",
)
async def list_models(
    limit: Optional[int] = Query(default=10, ge=1, le=100, description="Số item/trang (1–100)."),
    startAfter: Optional[str] = Query(default=None, description="rvcModelId làm cursor trang kế."),
    auth: AuthContext = Depends(authenticate_token),
):
    return await user_model_controller.list(
        user_id=auth.user_id,
        limit=limit,
        start_after=startAfter,
    )


@router.get(
    "/models/{rvc_model_id}",
    summary="Lấy chi tiết một model cá nhân theo ID",
)
async def get_detail(
    rvc_model_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await user_model_controller.detail(
        user_id=auth.user_id,
        rvc_model_id=rvc_model_id,
    )


@router.put(
    "/models/{rvc_model_id}",
    summary="Cập nhật metadata model cá nhân (title, description)",
)
async def update_one(
    rvc_model_id: str,
    body: UpdateUserModelRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await user_model_controller.update(
        rvc_model_id=rvc_model_id,
        body=body,
        auth=auth,
    )


@router.delete(
    "/models/{rvc_model_id}",
    summary="Xoá một model cá nhân (Firestore doc + storage folder)",
)
async def delete_one(
    rvc_model_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await user_model_controller.delete_one(
        rvc_model_id=rvc_model_id,
        auth=auth,
    )
