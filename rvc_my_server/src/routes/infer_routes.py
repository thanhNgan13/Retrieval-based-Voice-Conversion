from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from src.controllers.infer_controller import infer_controller
from src.middlewares.auth_middleware import AuthContext, authenticate_token

router = APIRouter()


@router.get(
    "/torch-status",
    summary="Kiểm tra PyTorch + GPU CUDA đã sẵn sàng cho infer chưa",
    description=(
        "Trả về thông tin chi tiết về môi trường runtime của container infer:\n"
        "- `nvidiaSmi`: driver version + CUDA version từ `nvidia-smi` (`null` nếu không có GPU NVIDIA).\n"
        "- `torch.installed`, `torch.version`, `torch.cudaBuild`: PyTorch đã cài và build CUDA tương ứng.\n"
        "- `torch.cudaAvailable`: PyTorch có nhận được GPU không — **trường quan trọng nhất**.\n"
        "- `torch.devices[]`: danh sách GPU kèm tên, VRAM, compute capability.\n"
        "- `torch.smokeTest`: thử cấp phát tensor nhỏ + phép cộng trên CUDA để xác nhận GPU thực sự dùng được.\n"
        "- `engine`: trạng thái VC engine — đã bootstrap chưa, đang dùng device gì, model nào đang load.\n\n"
        "Endpoint chỉ **đọc** trạng thái, không tự khởi tạo engine hay tải model."
    ),
)
async def torch_status(auth: AuthContext = Depends(authenticate_token)):
    return await infer_controller.torch_status()


@router.post(
    "/convert",
    summary="Đổi giọng audio nguồn sang giọng của RVC model đã chọn",
    description=(
        "Upload audio nguồn (`.wav`, `.mp3`, `.m4a`, ...) + `rvcModelId` để đổi giọng.\n\n"
        "Server sẽ:\n"
        "1. Tải `.pth` và `.index` từ Storage (cache local, lần sau không tải lại).\n"
        "2. Nạp model vào engine RVC (chỉ reload khi `rvcModelId` thay đổi so với request trước).\n"
        "3. Chạy pipeline RVC (Hubert → F0 → retrieval → net_g).\n"
        "4. Upload WAV kết quả lên Storage, trả `outputUrl` (Firebase download token URL).\n\n"
        "**Mọi tham số đều có default** — nếu không truyền sẽ dùng giá trị mặc định của RVC."
    ),
)
async def convert(
    audio: UploadFile = File(
        ...,
        description=(
            "File audio nguồn cần đổi giọng. Có thể là `.wav`, `.mp3`, `.m4a`, `.flac`, "
            "`.ogg`... FFmpeg nội bộ RVC sẽ resample về 16 kHz mono trước khi vào Hubert."
        ),
    ),
    rvcModelId: str = Form(
        ...,
        description=(
            "ID của RVC model dùng để đổi giọng. Lấy từ `GET /rvc-model-services` hoặc "
            "`GET /rvc-model-services/{id}`."
        ),
        examples=["rvc_1779180318216_7f0d47ae-364a-4e18-9944-ce53b2bf1f11"],
    ),
    speakerId: int = Form(
        default=0,
        ge=0,
        description=(
            "**SPEAKER_ID** — Chỉ số speaker trong model đa người nói (`emb_g`). "
            "Đa số model RVC chỉ train 1 speaker → giữ `0`. Tăng dần nếu model có nhiều giọng."
        ),
    ),
    f0UpKey: int = Form(
        default=0,
        ge=-24,
        le=24,
        description=(
            "**F0_UP_KEY** — Dịch tông giọng theo **nửa cung (semitone)**. "
            "`0` = giữ nguyên pitch nguồn. `+12` = lên 1 quãng tám, `-12` = xuống 1 quãng tám. "
            "Quy tắc nhanh: giọng nữ → giọng nam thường `-12`, ngược lại `+12`."
        ),
    ),
    f0Method: str = Form(
        default="rmvpe",
        description=(
            "**F0_METHOD** — Thuật toán ước lượng pitch (F0):\n"
            "- `pm`: nhanh nhất, kém chính xác (dùng khi máy yếu).\n"
            "- `harvest`: tốt với giọng trầm, chậm.\n"
            "- `crepe`: ML-based, chất lượng cao, **nặng GPU**.\n"
            "- `rmvpe` *(mặc định)*: cân bằng tốc độ + chất lượng. Cần file `assets/rmvpe/rmvpe.pt`."
        ),
        examples=["rmvpe"],
    ),
    indexRate: float = Form(
        default=0.75,
        ge=0.0,
        le=1.0,
        description=(
            "**INDEX_RATE** — Tỉ lệ trộn feature retrieval từ `.index` FAISS.\n"
            "Công thức: `feat = indexRate * feat_retrieved + (1 - indexRate) * feat_hubert`.\n"
            "- `0` = tắt retrieval (giọng đổi nhẹ, giữ đặc trưng nguồn).\n"
            "- `1` = full retrieval (giọng đích đậm nhưng có thể méo).\n"
            "- `0.75` *(mặc định)* = tự nhiên nhất trong đa số trường hợp."
        ),
    ),
    filterRadius: int = Form(
        default=3,
        ge=0,
        le=7,
        description=(
            "**FILTER_RADIUS** — Bán kính median filter cho đường F0. "
            "**Chỉ ảnh hưởng khi `f0Method=harvest`** — các method khác bỏ qua. "
            "Cao → đường F0 mượt hơn (giảm hiện tượng câm bất chợt) nhưng có thể mất biến điệu tinh tế. "
            "0–7, mặc định `3`."
        ),
    ),
    resampleSr: int = Form(
        default=0,
        ge=0,
        le=48000,
        description=(
            "**RESAMPLE_SR** — Sample rate đầu ra (Hz). "
            "`0` *(mặc định)* = giữ sample rate gốc của model (thường 32 000 / 40 000 / 48 000). "
            "`> 0` = resample WAV output về tần số này (chỉ có hiệu lực khi ≥ 16 000 theo logic RVC gốc)."
        ),
    ),
    rmsMixRate: float = Form(
        default=0.25,
        ge=0.0,
        le=1.0,
        description=(
            "**RMS_MIX_RATE** — Tỉ lệ trộn bao âm lượng (envelope RMS) của giọng nguồn vào kết quả.\n"
            "- `0` = giữ âm lượng đều của model (cảm giác 'phẳng').\n"
            "- `1` = bám sát âm lượng nguồn theo thời gian (tự nhiên hơn nhưng có thể méo).\n"
            "- `0.25` *(mặc định)* = nhấn nhẹ theo nguồn."
        ),
    ),
    protect: float = Form(
        default=0.33,
        ge=0.0,
        le=0.5,
        description=(
            "**PROTECT** — Bảo vệ phụ âm vô thanh / âm tĩnh để giảm artifact 'rè' khi đổi giọng. "
            "Phạm vi 0.0 – 0.5:\n"
            "- `0` = bảo vệ TỐI ĐA — phụ âm rõ nhưng giọng có thể không đổi nhiều.\n"
            "- `0.5` = **tắt** bảo vệ — model làm chủ hoàn toàn, có thể rè khi nói nhanh.\n"
            "- `0.33` *(mặc định RVC)* = cân bằng."
        ),
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await infer_controller.convert(
        audio_file=audio,
        rvc_model_id=rvcModelId,
        speaker_id=speakerId,
        f0_up_key=f0UpKey,
        f0_method=f0Method,
        index_rate=indexRate,
        filter_radius=filterRadius,
        resample_sr=resampleSr,
        rms_mix_rate=rmsMixRate,
        protect=protect,
        auth=auth,
    )


@router.post(
    "/convert/private",
    summary="Đổi giọng bằng private RVC model của user hiện tại",
    description=(
        "Upload audio nguồn + `rvcModelId` của model private thuộc user đang request.\n\n"
        "Khác với `/infer-services/convert`, API này chỉ tìm model trong "
        "`users/{currentUserId}/rvc_models/{rvcModelId}` và không fallback sang "
        "collection public `rvc_models`."
    ),
)
async def convert_private(
    audio: UploadFile = File(
        ...,
        description="File audio nguồn cần đổi giọng.",
    ),
    rvcModelId: str = Form(
        ...,
        description=(
            "ID của private RVC model thuộc user hiện tại. Lấy từ "
            "`GET /train-services/models` hoặc `GET /train-services/models/{id}`."
        ),
        examples=["rvc_1779180318216_7f0d47ae-364a-4e18-9944-ce53b2bf1f11"],
    ),
    speakerId: int = Form(
        default=0,
        ge=0,
        description="Speaker ID trong model đa người nói. Single-speaker dùng `0`.",
    ),
    f0UpKey: int = Form(
        default=0,
        ge=-24,
        le=24,
        description="Dịch tông giọng theo semitone. `0` = giữ nguyên pitch nguồn.",
    ),
    f0Method: str = Form(
        default="rmvpe",
        description="Thuật toán F0: `pm`, `harvest`, `crepe`, hoặc `rmvpe`.",
        examples=["rmvpe"],
    ),
    indexRate: float = Form(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Tỉ lệ trộn feature retrieval từ `.index` FAISS.",
    ),
    filterRadius: int = Form(
        default=3,
        ge=0,
        le=7,
        description="Bán kính median filter cho F0, chủ yếu ảnh hưởng khi `f0Method=harvest`.",
    ),
    resampleSr: int = Form(
        default=0,
        ge=0,
        le=48000,
        description="Sample rate đầu ra. `0` = giữ sample rate gốc của model.",
    ),
    rmsMixRate: float = Form(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Tỉ lệ trộn bao âm lượng RMS của nguồn vào kết quả.",
    ),
    protect: float = Form(
        default=0.33,
        ge=0.0,
        le=0.5,
        description="Bảo vệ phụ âm vô thanh / âm tĩnh để giảm artifact.",
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await infer_controller.convert_private(
        audio_file=audio,
        rvc_model_id=rvcModelId,
        speaker_id=speakerId,
        f0_up_key=f0UpKey,
        f0_method=f0Method,
        index_rate=indexRate,
        filter_radius=filterRadius,
        resample_sr=resampleSr,
        rms_mix_rate=rmsMixRate,
        protect=protect,
        auth=auth,
    )


@router.post(
    "/mix",
    summary="Mix giọng AI đã convert với backing vocal và nhạc nền theo notebook audio_mixing_guide",
    description=(
        "Upload giọng AI đã đổi (`mainVocal`) cùng `backupVocal` và `instrumental` nếu có. "
        "Server chạy đúng pipeline trong `audio_mixing_guide.ipynb`:\n"
        "1. Áp dụng `HighpassFilter()` + `Compressor(ratio=4, threshold_db=-15)` + "
        "`Reverb(...)` lên main vocal, đọc theo block 1 giây.\n"
        "2. Dùng pydub để mix: main vocal wet `-4 dB + mainGain`, backup "
        "`-6 dB + backupGain`, instrumental `-7 dB + instGain`.\n"
        "3. Upload `aiVocalsWet` và `finalMix` lên Firebase Storage.\n\n"
        "`backupVocal` và `instrumental` là optional giống notebook: nếu thiếu, server tạo "
        "track câm có cùng độ dài với main vocal."
    ),
)
async def mix(
    mainVocal: UploadFile = File(
        ...,
        description=(
            "File giọng AI đã convert từ RVC. Đây là `ai_vocals_dry_path` trong notebook."
        ),
    ),
    backupVocal: Optional[UploadFile] = File(
        default=None,
        description=(
            "File giọng bè tách từ stage 2 separation. Nếu không truyền, server dùng track câm."
        ),
    ),
    instrumental: Optional[UploadFile] = File(
        default=None,
        description=(
            "File nhạc nền/beat tách từ stage 1 separation. Nếu không truyền, server dùng track câm."
        ),
    ),
    reverbRoomSize: float = Form(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Notebook `reverb_room_size`: kích thước phòng của Reverb.",
    ),
    reverbWetLevel: float = Form(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Notebook `reverb_wet_level`: độ lớn tiếng vang.",
    ),
    reverbDryLevel: float = Form(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Notebook `reverb_dry_level`: độ lớn giọng gốc giữ lại.",
    ),
    reverbDamping: float = Form(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Notebook `reverb_damping`: giảm độ chói của tiếng vang.",
    ),
    mainGain: float = Form(
        default=0,
        description=(
            "Notebook `main_gain` tính bằng dB. Server vẫn áp dụng offset gốc `-4 dB` "
            "trước rồi mới cộng giá trị này."
        ),
    ),
    backupGain: float = Form(
        default=0,
        description=(
            "Notebook `backup_gain` tính bằng dB. Server vẫn áp dụng offset gốc `-6 dB` "
            "trước rồi mới cộng giá trị này."
        ),
    ),
    instGain: float = Form(
        default=0,
        description=(
            "Notebook `inst_gain` tính bằng dB. Server vẫn áp dụng offset gốc `-7 dB` "
            "trước rồi mới cộng giá trị này."
        ),
    ),
    outputFormat: str = Form(
        default="wav",
        description=(
            "Notebook `output_format`. Hỗ trợ `wav` hoặc `mp3`; `wav` là default."
        ),
        examples=["wav"],
    ),
    keepLocal: bool = Query(
        default=False,
        description="Chỉ dùng để debug: giữ lại workspace local trong cache thay vì xoá sau khi upload.",
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await infer_controller.mix(
        main_vocal_file=mainVocal,
        backup_vocal_file=backupVocal,
        instrumental_file=instrumental,
        reverb_room_size=reverbRoomSize,
        reverb_wet=reverbWetLevel,
        reverb_dry=reverbDryLevel,
        reverb_damping=reverbDamping,
        main_gain=mainGain,
        backup_gain=backupGain,
        inst_gain=instGain,
        output_format=outputFormat,
        keep_local=keepLocal,
        auth=auth,
    )

