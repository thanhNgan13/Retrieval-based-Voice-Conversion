import asyncio
import json
import time
from typing import Literal, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from src.config.settings import settings
from src.controllers.train_controller import train_controller
from src.middlewares.auth_middleware import (
    AuthContext,
    authenticate_token,
    verify_user_access_token,
)
from src.schemas.train_schema import (
    CreateTrainJobRequest,
    CreateTrainUploadUrlsRequest,
    DeleteTrainingUploadsRequest,
)
from src.services.train_service import get_train_job_detail

router = APIRouter()


TRAIN_JOB_DESCRIPTION = """
Tạo Celery training job từ các audio object paths đã upload lên Firebase Storage.
Job chạy nền, progress realtime qua WebSocket:
`/train-services/jobs/{trainJobId}/ws?token=<accessToken>`.

**Trình tự gọi**

1. `POST /train-services/upload-urls`
2. `PUT` audio binary lên từng `uploadUrl`
3. `POST /train-services/jobs` với các `audioUploadIds` hoặc `audioObjectPaths`
4. Theo dõi bằng WebSocket hoặc `GET /train-services/jobs/{trainJobId}`
5. Khi `status=succeeded`, dùng `rvcModelId` để gọi `/infer-services/convert`

**Tham số request body**

| Field | Kiểu / Giá trị hợp lệ | Default | Ý nghĩa |
|---|---:|---:|---|
| `title` | string, 1-120 chars | required | Tên model private sau khi train xong. |
| `description` | string, 0-2000 chars | `""` | Mô tả model, không ảnh hưởng training. |
| `audioUploadIds` | array string, 1-20 items | optional | ID audio upload trả về từ `/upload-urls`. Khuyến nghị dùng field này để request gọn hơn. |
| `audioObjectPaths` | array string, 1-20 items | optional | Storage paths lấy từ `/upload-urls`, giữ để tương thích. Cần truyền `audioUploadIds` hoặc `audioObjectPaths`. |
| `sampleRate` | `32k`, `40k`, `48k` | `40k` | Sample rate output của model. `40k` cân bằng, `48k` nặng hơn, `32k` nhẹ hơn. |
| `version` | `v1`, `v2` | `v2` | Kiến trúc RVC. Nên dùng `v2` cho model mới. |
| `ifF0` | boolean | `true` | Bật nhánh pitch/F0. Nên bật cho voice conversion tự nhiên. |
| `f0Method` | `pm`, `harvest`, `dio`, `rmvpe`, `rmvpe_gpu` | `rmvpe` | Thuật toán extract pitch. `rmvpe` là lựa chọn mặc định tốt. |
| `totalEpochs` | int, 1-1000 | `50` | Tổng số epoch. Test nhanh dùng 5-20; train thật thường 50-300. |
| `saveEveryEpoch` | int, 1-1000 | `5` | Chu kỳ lưu checkpoint G_/D_. |
| `batchSize` | int, 1-64 | `4` | Batch size. Tăng nhanh hơn nhưng tốn VRAM. GPU yếu dùng 1-4. |
| `numProcesses` | int, 1-32 | `4` | Số process CPU cho preprocess/F0. |
| `gpuDevicesTrain` | string pattern `0` hoặc `0-1` | `0` | GPU ids dùng cho training. |
| `gpusForRmvpe` | string pattern `0`, `0-1`, hoặc `-` | `0` | GPU ids dùng cho `rmvpe_gpu`; `-` dùng DirectML path. |
| `speakerId` | int, >= 0 | `0` | Speaker id ghi vào filelist. Single-speaker dùng `0`. |
| `saveOnlyLatest` | boolean | `true` | Chỉ giữ checkpoint mới nhất để tiết kiệm disk. |
| `cacheDatasetInGpu` | boolean | `false` | Cache dataset vào GPU. Nhanh hơn nhưng dễ thiếu VRAM. |
| `saveWeightsEveryEpoch` | boolean | `false` | Extract inference weight mỗi lần save checkpoint. Tốn disk hơn. |
| `pretrainedG` | string, path dưới `assets/` hoặc `""` | `""` | Pretrained Generator. Rỗng thì auto chọn theo sampleRate/version/ifF0. |
| `pretrainedD` | string, path dưới `assets/` hoặc `""` | `""` | Pretrained Discriminator. Rỗng thì auto chọn. |
| `preprocessPer` | float, 1.0-10.0 | `3.7` | Độ dài mỗi slice audio khi preprocess, tính bằng giây. |
| `disablePreprocessParallel` | boolean | `false` | Tắt multiprocessing preprocess, hữu ích khi debug. |
| `extractInfo` | string, 0-500 chars | `Extracted model.` | Metadata ghi vào `model.pth`. |
| `indexKmeansThreshold` | int, 10000-2000000 | `200000` | Nếu số vector Hubert vượt ngưỡng này, dùng KMeans trước khi build index. |
| `indexKmeansCenters` | int, 100-100000 | `10000` | Số cluster center khi KMeans. Cao hơn giữ nhiều thông tin hơn nhưng chậm hơn. |
| `indexBatchSize` | int, 1024-65536 | `8192` | Số vector add vào FAISS mỗi batch. |
| `indexNprobe` | int, 1-64 | `1` | FAISS IVF nprobe. Cao hơn có thể retrieval tốt hơn nhưng inference chậm hơn. |
"""


@router.post(
    "/upload-urls",
    summary="Create signed PUT URLs for training audio upload",
    description=(
        "Client uploads audio directly to Firebase Storage using the returned signed PUT URLs. "
        "Then pass returned `objectPath` values to POST /train-services/jobs."
    ),
)
async def create_upload_urls(
    body: CreateTrainUploadUrlsRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.create_upload_urls(body, auth)


@router.post(
    "/jobs",
    summary="Queue a private RVC training job",
    description=TRAIN_JOB_DESCRIPTION,
)
async def create_job(
    body: CreateTrainJobRequest,
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.create_job(body, auth)


@router.get("/jobs", summary="List current user's training jobs")
async def list_jobs(
    limit: Optional[int] = Query(default=10, ge=1, le=100),
    startAfter: Optional[str] = Query(default=None),
    status: Optional[Literal["queued", "running", "succeeded", "failed", "active"]] = Query(
        default=None,
        description=(
            "Lọc job theo trạng thái. "
            "`succeeded` = đã hoàn thành; "
            "`active` = đang tiến hành (queued + running); "
            "`queued` = đang chờ trong hàng; "
            "`running` = đang chạy; "
            "`failed` = thất bại. "
            "Bỏ trống = trả tất cả."
        ),
    ),
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.list_jobs(limit, startAfter, status, auth)


@router.get("/jobs/{train_job_id}", summary="Get training job detail")
async def job_detail(
    train_job_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.job_detail(train_job_id, auth)


@router.get(
    "/uploads",
    summary="List current user's uploaded training audio files",
    description=(
        "Liệt kê các file audio user đã upload qua signed URL dưới "
        "`train_uploads/{userId}/...`. Mỗi item trả kèm `audioUrl` là signed GET URL "
        "tạm thời để app có thể phát/nghe file audio. URL hết hạn theo "
        "`SIGNED_DOWNLOAD_URL_EXPIRES_SECONDS`."
    ),
)
async def list_uploads(auth: AuthContext = Depends(authenticate_token)):
    return await train_controller.list_uploads(auth)


@router.post(
    "/uploads/delete",
    summary="Delete uploaded training audio files",
    description=(
        "Một API dùng cho cả 2 case. Nếu query `deleteAll=true`, server xoá toàn bộ "
        "uploads của user và bỏ qua request body. Nếu `deleteAll=false`, request body "
        "bắt buộc có `audioUploadIds` hoặc `objectPaths` để xoá 1/nhiều file. "
        "Khuyến nghị dùng `audioUploadIds`. Server chỉ cho xoá object dưới "
        "`train_uploads/{currentUserId}/` để user không xoá file của người khác."
    ),
)
async def delete_uploads(
    deleteAll: bool = Query(
        default=False,
        description=(
            "true = xoá toàn bộ uploads của user và không cần body; "
            "false = xoá theo objectPaths trong body."
        ),
    ),
    body: Optional[DeleteTrainingUploadsRequest] = None,
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.delete_uploads(deleteAll, body, auth)


@router.websocket("/jobs/{train_job_id}/ws")
async def training_progress_ws(websocket: WebSocket, train_job_id: str):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        auth = verify_user_access_token(token)
        snapshot = get_train_job_detail(train_job_id, auth.user_id)
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await websocket.send_json({"type": "snapshot", "data": snapshot})
    if snapshot.get("status") in {"succeeded", "failed"}:
        await websocket.send_json({"type": "terminal", "data": snapshot})
        await websocket.close(code=1000)
        return

    redis_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"rvc_train_job:{train_job_id}")
    # Pub/Sub is the live source of truth. Firestore poll is only a safety net for
    # the rare case a publish is lost (network blip, Redis restart) — runs every
    # SAFETY_POLL_INTERVAL seconds, not every loop, to avoid duplicate events.
    SAFETY_POLL_INTERVAL = 30.0
    PUBSUB_TIMEOUT = 5.0
    last_safety_check = time.monotonic()
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=PUBSUB_TIMEOUT,
            )
            if message and message.get("type") == "message":
                payload = json.loads(message["data"])
                await websocket.send_json({"type": "progress", "data": payload})
                if payload.get("status") in {"succeeded", "failed"}:
                    await websocket.send_json({"type": "terminal", "data": payload})
                    break
                continue

            now = time.monotonic()
            if now - last_safety_check >= SAFETY_POLL_INTERVAL:
                last_safety_check = now
                latest = get_train_job_detail(train_job_id, auth.user_id)
                if latest.get("status") in {"succeeded", "failed"}:
                    await websocket.send_json({"type": "terminal", "data": latest})
                    break
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "data": {
                            "trainJobId": train_job_id,
                            "status": latest.get("status"),
                            "stage": latest.get("stage"),
                            "progress": latest.get("progress"),
                            "elapsedMs": latest.get("elapsedMs", 0),
                        },
                    }
                )
            else:
                await websocket.send_json(
                    {"type": "heartbeat", "data": {"trainJobId": train_job_id}}
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {
                        "message": str(exc),
                    },
                }
            )
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(f"rvc_train_job:{train_job_id}")
        await pubsub.close()
        await redis_client.close()


@router.get("/models", summary="List current user's private trained RVC models")
async def list_models(
    limit: Optional[int] = Query(default=10, ge=1, le=100),
    startAfter: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.list_models(limit, startAfter, auth)


@router.get(
    "/models/{rvc_model_id}",
    summary="Get private trained RVC model detail with signed download URLs",
)
async def model_detail(
    rvc_model_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    return await train_controller.model_detail(rvc_model_id, auth)
