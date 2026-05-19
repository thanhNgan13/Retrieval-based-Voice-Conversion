from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.admin_controller import admin_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token_admin
from src.schemas.admin_schema import AdminLoginRequest, AdminRefreshTokenRequest

# Long-running download (Hubert ~360 MB + RMVPE ~180 MB).
_SETUP_ASSETS_TIMEOUT_NOTE = (
    "Endpoint này tải file lớn từ Hugging Face — có thể mất vài phút tuỳ băng thông. "
    "Lần gọi sau khi file đã có sẽ trả về ngay (status `already_present`)."
)

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


@router.post(
    "/setup-assets",
    summary="Tải các model mặc định cần cho infer (Hubert + RMVPE)",
    description=(
        "Kiểm tra `assets/hubert/hubert_base.pt` và `assets/rmvpe/rmvpe.pt`. "
        "File nào thiếu sẽ tải từ Hugging Face (`lj1995/VoiceConversionWebUI`). "
        "Sau khi gọi thành công, API `/infer-services/convert` chỉ cần tải đúng "
        "RVC model `.pth/.index` của request là chạy được.\n\n"
        + _SETUP_ASSETS_TIMEOUT_NOTE
        + "\n\nĐặt env `RVC_HF_MIRROR=1` nếu mạng truy cập huggingface.co không ổn định "
        "(sẽ dùng `hf-mirror.com`)."
    ),
)
async def setup_assets(
    force: bool = Query(
        default=False,
        description=(
            "`true` = tải lại kể cả file đã tồn tại (dùng khi nghi ngờ file cũ corrupt). "
            "`false` *(mặc định)* = bỏ qua file đã có."
        ),
    ),
    _: AuthContext = Depends(authenticate_token_admin),
):
    return await admin_controller.setup_assets(force=force)


@router.get(
    "/assets-status",
    summary="Kiểm tra trạng thái các asset cần cho infer (không tải)",
    description="Trả về `present`/`absent` cho từng asset mặc định (Hubert, RMVPE).",
)
async def assets_status(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.get_assets_status()


@router.get(
    "/torch-status",
    summary="Kiểm tra PyTorch + GPU CUDA đã sẵn sàng cho infer chưa",
    description=(
        "Trả về thông tin chi tiết:\n"
        "- `nvidiaSmi`: driver + CUDA version từ `nvidia-smi` (null nếu máy không có NVIDIA).\n"
        "- `torch.installed`, `torch.version`, `torch.cudaBuild`: PyTorch wheel đã cài.\n"
        "- `torch.cudaAvailable`: PyTorch có nhận GPU không (quan trọng nhất).\n"
        "- `torch.devices[]`: tên GPU, VRAM, compute capability.\n"
        "- `torch.smokeTest`: thử alloc tensor + phép cộng trên CUDA (xác nhận thực sự chạy được).\n"
        "- `engine`: trạng thái VC engine đã bootstrap chưa, đang dùng device gì.\n\n"
        "Endpoint không tự khởi tạo VC engine — chỉ đọc trạng thái hiện tại."
    ),
)
async def torch_status(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.torch_status()
