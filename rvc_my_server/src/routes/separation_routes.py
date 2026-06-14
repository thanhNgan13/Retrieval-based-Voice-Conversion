from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.controllers.separation_controller import separation_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token

router = APIRouter()


@router.get(
    "/models",
    summary="Kiem tra 3 model MDX-Net ONNX dung cho pipeline separation",
    description=(
        "Tra ve trang thai cua 3 model dung dung theo notebook "
        "`audio_separation_guide.ipynb`: "
        "`UVR-MDX-NET-Voc_FT.onnx`, `UVR_MDXNET_KARA_2.onnx`, "
        "`Reverb_HQ_By_FoxJoy.onnx`."
    ),
)
async def models(auth: AuthContext = Depends(authenticate_token)):
    return await separation_controller.models()


@router.post(
    "/separate",
    summary="Tach bai hat bang pipeline MDX-Net 3 giai doan trong notebook",
    description=(
        "Upload mot file bai hat. Server chay dung pipeline trong "
        "`audio_separation_guide.ipynb`:\n"
        "1. `UVR-MDX-NET-Voc_FT.onnx`: tach `instrumental` va vocal tam.\n"
        "2. `UVR_MDXNET_KARA_2.onnx`: tach `backupVocals` va main vocal tam.\n"
        "3. `Reverb_HQ_By_FoxJoy.onnx`: tao `mainVocalsDereverb`.\n\n"
        "Tat ca output la WAV va duoc upload len Firebase Storage."
    ),
)
async def separate(
    audio: UploadFile = File(
        ...,
        description="File bai hat can tach nguon am thanh.",
    ),
    keepLocal: bool = Query(
        default=False,
        description="Debug only: giu workspace local trong cache thay vi xoa sau khi upload.",
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await separation_controller.separate(
        audio_file=audio,
        keep_local=keepLocal,
        auth=auth,
    )
