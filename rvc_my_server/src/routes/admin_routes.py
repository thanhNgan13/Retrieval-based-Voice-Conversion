from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.controllers.admin_controller import admin_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token_admin
from src.schemas.admin_schema import AdminLoginRequest, AdminRefreshTokenRequest

# Long-running download (Hubert ~360 MB + RMVPE ~180 MB).
_SETUP_ASSETS_TIMEOUT_NOTE = (
    "Endpoint này tải file lớn từ Hugging Face hoặc mirror — có thể mất vài phút tuỳ băng thông. "
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


@router.post(
    "/setup-mdxnet-assets",
    summary="Tải 3 model MDX-Net ONNX dùng cho tách âm thanh",
    description=(
        "Kiểm tra thư mục `mdxnet_models`. File nào thiếu sẽ tải từ GitHub release "
        "`TRvlvr/model_repo/all_public_uvr_models`, gồm 3 model dùng trong pipeline tách âm 3 giai đoạn: "
        "`UVR-MDX-NET-Voc_FT.onnx` (tách giọng/nhạc nền), `UVR_MDXNET_KARA_2.onnx` (tách giọng chính/bè), "
        "`Reverb_HQ_By_FoxJoy.onnx` (khử reverb).\n\n"
        + _SETUP_ASSETS_TIMEOUT_NOTE
    ),
)
async def setup_mdxnet_assets(
    force: bool = Query(
        default=False,
        description=(
            "`true` = tải lại kể cả file đã tồn tại. "
            "`false` *(mặc định)* = bỏ qua file đã có."
        ),
    ),
    _: AuthContext = Depends(authenticate_token_admin),
):
    return await admin_controller.setup_mdxnet_assets(force=force)


@router.get(
    "/mdxnet-assets-status",
    summary="Kiểm tra trạng thái asset MDX-Net ONNX (không tải)",
    description="Trả về `present`/`absent` cho 3 model ONNX trong thư mục `mdxnet_models`.",
)
async def mdxnet_assets_status(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.get_mdxnet_assets_status()


@router.get(
    "/training-assets-status",
    summary="Kiểm tra asset cần cho training RVC (không cài/tải)",
    description=(
        "Kiểm tra đầy đủ các asset cần cho training:\n"
        "- `assets/hubert/hubert_base.pt`\n"
        "- `assets/rmvpe/rmvpe.pt`\n"
        "- toàn bộ pretrained G/D cho `pretrained` và `pretrained_v2` ở 32k/40k/48k\n"
        "- `logs/mute/*` template (chỉ kiểm tra, nếu thiếu phải copy thủ công)\n"
        "- thư mục `assets/weights`\n\n"
        "Endpoint này chỉ kiểm tra, không tải file."
    ),
)
async def training_assets_status(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.get_training_assets_status()


@router.post(
    "/backfill-covers",
    summary="Backfill list_cover từ các song inference job đã succeeded",
    description=(
        "Quét toàn bộ job có `status=succeeded`, tạo entry trong collection `list_cover` "
        "cho những job chưa có cover. Dùng khi deploy tính năng cover management sau khi "
        "các job đã chạy xong (Celery worker cũ chưa có `save_completed_cover`)."
    ),
)
async def backfill_covers(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.backfill_covers()


@router.post(
    "/migrate-covers-song-info",
    summary="Thêm song_info vào các cover cũ thiếu thông tin bài hát",
    description=(
        "Quét toàn bộ cover trong `list_cover`, tìm các cover được tạo từ song_id "
        "nhưng chưa có `source_song.song_info`, rồi lấy dữ liệu từ job document tương ứng "
        "và cập nhật vào Firestore. Chạy một lần sau khi deploy fix song_info."
    ),
)
async def migrate_covers_song_info(_: AuthContext = Depends(authenticate_token_admin)):
    return await admin_controller.migrate_covers_song_info()


@router.post(
    "/setup-training-assets",
    summary="Cài/tải các asset cần cho training RVC",
    description=(
        "Cài đầy đủ asset training nếu thiếu. Luồng cài:\n"
        "1. Hubert/RMVPE: dùng lại logic `/setup-assets`.\n"
        "2. Pretrained G/D: tải trực tiếp từ Hugging Face hoặc mirror giống luồng asset của RVC, "
        "không copy từ `rvc_standalone`.\n"
        "3. `logs/mute`: chỉ kiểm tra. Nếu thiếu, response sẽ liệt kê file thiếu và log nhắc "
        "copy thủ công từ full RVC/rvc_standalone; endpoint không tự copy/tự tạo.\n"
        "4. Tạo `assets/weights`.\n\n"
        + _SETUP_ASSETS_TIMEOUT_NOTE
        + "\n\nĐặt env `RVC_HF_MIRROR=1` nếu mạng truy cập huggingface.co không ổn định."
    ),
)
async def setup_training_assets(
    force: bool = Query(
        default=False,
        description=(
            "`true` = cài/tải lại kể cả file đã tồn tại. "
            "`false` = chỉ cài phần còn thiếu."
        ),
    ),
    _: AuthContext = Depends(authenticate_token_admin),
):
    return await admin_controller.setup_training_assets(force=force)
