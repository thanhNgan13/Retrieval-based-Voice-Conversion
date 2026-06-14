from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.controllers.separation_controller import separation_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token

router = APIRouter()


@router.get(
    "/models",
    summary="Kiểm tra 3 model MDX-Net ONNX dùng cho pipeline tách âm thanh",
    description=(
        "Trả về trạng thái của 3 model trong thư mục `mdxnet_models`: "
        "`UVR-MDX-NET-Voc_FT.onnx`, `UVR_MDXNET_KARA_2.onnx`, "
        "`Reverb_HQ_By_FoxJoy.onnx`. "
        "Nếu thiếu model, gọi admin `/setup-mdxnet-assets` để tải về trước."
    ),
)
async def models(auth: AuthContext = Depends(authenticate_token)):
    return await separation_controller.models()


@router.post(
    "/separate",
    summary="Tách bài hát bằng pipeline MDX-Net 3 giai đoạn",
    description=(
        "Upload một file bài hát. Server chạy pipeline tách âm 3 giai đoạn:\n"
        "1. `UVR-MDX-NET-Voc_FT.onnx`: tách `instrumental` và giọng hát tạm.\n"
        "2. `UVR_MDXNET_KARA_2.onnx`: tách `backupVocals` và giọng chính tạm.\n"
        "3. `Reverb_HQ_By_FoxJoy.onnx`: khử reverb, tạo `mainVocalsDereverb`.\n\n"
        "Tất cả output là WAV và được upload lên Firebase Storage."
    ),
)
async def separate(
    audio: UploadFile = File(
        ...,
        description="File bài hát cần tách nguồn âm thanh.",
    ),
    keepLocal: bool = Query(
        default=False,
        description="Chỉ dùng để debug: giữ lại workspace local trong cache thay vì xoá sau khi upload.",
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await separation_controller.separate(
        audio_file=audio,
        keep_local=keepLocal,
        auth=auth,
    )
