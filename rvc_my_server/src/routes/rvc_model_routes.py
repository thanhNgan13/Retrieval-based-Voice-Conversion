from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from src.controllers.rvc_model_controller import rvc_model_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token_admin
from src.schemas.rvc_model_schema import UpdateRvcModelRequest

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload a new RVC model (.pth + .index + thumbnail)",
    description=(
        "Upload model files vào Storage và lưu metadata vào Firestore. "
        "File sẽ được chuẩn hoá thành `model.pth` và `model.index` trong thư mục "
        "`public_rvc_model/{rvcModelId}_{titleSlug}/`."
    ),
)
async def upload(
    title: str = Form(..., min_length=1, max_length=120, examples=["Giọng nam ấm áp"]),
    description: str = Form("", max_length=2000, examples=["Giọng nam trầm, phù hợp đọc sách nói."]),
    modelFile: UploadFile = File(..., description="File trọng số .pth của RVC model"),
    indexFile: UploadFile = File(..., description="File .index FAISS của RVC model"),
    thumbnail: Optional[UploadFile] = File(default=None, description="Ảnh thumbnail (jpg/jpeg/png/webp). Tuỳ chọn."),
    auth: AuthContext = Depends(authenticate_token_admin),
):
    return await rvc_model_controller.upload(
        title=title,
        description=description,
        model_file=modelFile,
        index_file=indexFile,
        thumbnail=thumbnail,
        auth=auth,
    )


@router.get(
    "",
    summary="List RVC models with cursor-based pagination",
)
async def list_models(
    limit: Optional[int] = Query(default=10, ge=1, le=100, description="Số item/trang (1–100)."),
    startAfter: Optional[str] = Query(default=None, description="rvcModelId làm cursor trang kế."),
):
    return await rvc_model_controller.list(limit=limit, start_after=startAfter)


@router.delete(
    "",
    summary="Delete ALL RVC models — DANGEROUS",
    description="Xoá toàn bộ document trong `rvc_models` và toàn bộ blob dưới `public_rvc_model/`.",
)
async def delete_all(auth: AuthContext = Depends(authenticate_token_admin)):
    return await rvc_model_controller.delete_all(auth)


@router.get(
    "/{rvc_model_id}",
    summary="Get RVC model detail by id",
)
async def get_detail(rvc_model_id: str):
    return await rvc_model_controller.detail(rvc_model_id)


@router.put(
    "/{rvc_model_id}",
    summary="Update RVC model metadata (title, description)",
)
async def update_one(
    rvc_model_id: str,
    body: UpdateRvcModelRequest,
    auth: AuthContext = Depends(authenticate_token_admin),
):
    return await rvc_model_controller.update(rvc_model_id, body, auth)


@router.delete(
    "/{rvc_model_id}",
    summary="Delete one RVC model (Firestore doc + storage folder)",
)
async def delete_one(
    rvc_model_id: str,
    auth: AuthContext = Depends(authenticate_token_admin),
):
    return await rvc_model_controller.delete_one(rvc_model_id, auth)
