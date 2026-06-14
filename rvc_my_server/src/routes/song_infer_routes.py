import json
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect

from src.config.settings import settings
from src.middlewares.auth_middleware import (
    AuthContext,
    authenticate_token,
    verify_user_access_token,
)
from src.services.song_infer_errors import (
    InvalidSongInferRequestError,
    SongInferJobNotFoundError,
)
from src.services.song_infer_progress import song_infer_channel
from src.services.song_infer_service import (
    create_song_infer_job,
    get_song_infer_job_detail,
    list_song_infer_jobs,
)
from src.utils.send_response import send_error_response, send_success_response

router = APIRouter()


SONG_INFER_JOB_DESCRIPTION = """
Tạo job xử lý đầy đủ một bài hát từ giọng A sang giọng B:

1. **Separation**: tách bài hát thành `instrumental`, `backupVocals`, `mainVocalsDereverb`
   bằng pipeline MDX-Net 3 stage như `audio_separation_guide.ipynb`.
2. **Infer / Convert**: dùng `mainVocalsDereverb` làm input cho RVC `vc_single`,
   chuyển sang `rvcModelId` đã chọn.
3. **Mixing**: áp dụng Highpass + Compressor + Reverb cho vocal đã convert,
   rồi overlay với backup vocal và instrumental như `audio_mixing_guide.ipynb`.

Job chạy nền qua Celery worker GPU, còn create/list/detail/WebSocket chạy ở
`api-light` port 8000:
`/song-infer-services/jobs/{songInferJobId}/ws?token=<accessToken>`.

**Separation params**

| Field | Kiểu | Default | Ý nghĩa |
|---|---:|---:|---|
| `separationDenoise` | bool | `true` | Dùng denoise mode của MDX-Net. |
| `separationKeepLocal` | bool | `false` | Debug: giữ workspace local của job. |

**Infer params**

| Field | Kiểu | Default | Ý nghĩa |
|---|---:|---:|---|
| `privateOnly` | bool | `false` | Chỉ tìm model private của user hiện tại. |
| `speakerId` | int >= 0 | `0` | Speaker id trong model đa speaker. |
| `f0UpKey` | int -24..24 | `0` | Dịch pitch theo semitone. |
| `f0Method` | `pm`, `harvest`, `crepe`, `rmvpe` | `rmvpe` | Thuật toán F0. |
| `indexRate` | float 0..1 | `0.75` | Mức dùng FAISS index retrieval. |
| `filterRadius` | int 0..7 | `3` | Median filter F0. |
| `resampleSr` | int 0..48000 | `0` | Sample rate output RVC. |
| `rmsMixRate` | float 0..1 | `0.25` | Mức bám envelope RMS nguồn. |
| `protect` | float 0..0.5 | `0.33` | Bảo vệ phụ âm/âm vô thanh. |

**Mixing params**

| Field | Kiểu | Default | Ý nghĩa |
|---|---:|---:|---|
| `reverbRoomSize` | float 0..1 | `0.15` | Kích thước phòng của Reverb. |
| `reverbWetLevel` | float 0..1 | `0.20` | Độ lớn tiếng vang. |
| `reverbDryLevel` | float 0..1 | `0.80` | Độ lớn tín hiệu gốc giữ lại. |
| `reverbDamping` | float 0..1 | `0.70` | Giảm độ chói của tiếng vang. |
| `mainGain` | float dB | `0` | Cộng thêm vào vocal chính sau offset notebook `-4 dB`. |
| `backupGain` | float dB | `0` | Cộng thêm vào backup vocal sau offset notebook `-6 dB`. |
| `instGain` | float dB | `0` | Cộng thêm vào instrumental sau offset notebook `-7 dB`. |
| `outputFormat` | `wav`, `mp3` | `wav` | Định dạng final mix. |
| `mixingKeepLocal` | bool | `false` | Debug: giữ workspace local của job. |
"""


@router.post(
    "/jobs",
    summary="Queue job separation -> infer -> mixing cho một bài hát",
    description=SONG_INFER_JOB_DESCRIPTION,
)
async def create_song_job(
    song: UploadFile = File(..., description="File bài hát gốc giọng A."),
    rvcModelId: str = Form(..., description="ID RVC model giọng B."),
    separationDenoise: bool = Form(default=True),
    separationKeepLocal: bool = Form(default=False),
    privateOnly: bool = Form(default=False),
    speakerId: int = Form(default=0, ge=0),
    f0UpKey: int = Form(default=0, ge=-24, le=24),
    f0Method: str = Form(default="rmvpe"),
    indexRate: float = Form(default=0.75, ge=0.0, le=1.0),
    filterRadius: int = Form(default=3, ge=0, le=7),
    resampleSr: int = Form(default=0, ge=0, le=48000),
    rmsMixRate: float = Form(default=0.25, ge=0.0, le=1.0),
    protect: float = Form(default=0.33, ge=0.0, le=0.5),
    reverbRoomSize: float = Form(default=0.15, ge=0.0, le=1.0),
    reverbWetLevel: float = Form(default=0.20, ge=0.0, le=1.0),
    reverbDryLevel: float = Form(default=0.80, ge=0.0, le=1.0),
    reverbDamping: float = Form(default=0.70, ge=0.0, le=1.0),
    mainGain: float = Form(default=0),
    backupGain: float = Form(default=0),
    instGain: float = Form(default=0),
    outputFormat: str = Form(default="wav"),
    mixingKeepLocal: bool = Form(default=False),
    auth: AuthContext = Depends(authenticate_token),
):
    params = {
        "separation": {
            "denoise": separationDenoise,
            "keepLocal": separationKeepLocal,
            "pipeline": "MDX-Net 3-stage notebook pipeline",
            "sampleRate": 44100,
            "models": {
                "vocal": "UVR-MDX-NET-Voc_FT.onnx",
                "karaoke": "UVR_MDXNET_KARA_2.onnx",
                "dereverb": "Reverb_HQ_By_FoxJoy.onnx",
            },
        },
        "infer": {
            "privateOnly": privateOnly,
            "speakerId": speakerId,
            "f0UpKey": f0UpKey,
            "f0Method": f0Method,
            "indexRate": indexRate,
            "filterRadius": filterRadius,
            "resampleSr": resampleSr,
            "rmsMixRate": rmsMixRate,
            "protect": protect,
        },
        "mixing": {
            "keepLocal": mixingKeepLocal,
            "reverbRoomSize": reverbRoomSize,
            "reverbWetLevel": reverbWetLevel,
            "reverbDryLevel": reverbDryLevel,
            "reverbDamping": reverbDamping,
            "mainGain": mainGain,
            "backupGain": backupGain,
            "instGain": instGain,
            "outputFormat": outputFormat,
            "notebookBaseMainDb": -4,
            "notebookBaseBackupDb": -6,
            "notebookBaseInstrumentalDb": -7,
            "effects": {
                "highpassFilter": {"enabled": True},
                "compressor": {"ratio": 4, "thresholdDb": -15},
            },
        },
    }
    try:
        result = create_song_infer_job(song, rvcModelId, auth.user_id, params)
        return send_success_response(201, "Song inference job queued", result)
    except InvalidSongInferRequestError as exc:
        return send_error_response(400, "VALIDATION_FAILED", str(exc))
    except Exception as exc:
        return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


@router.get("/jobs", summary="List current user's song inference jobs")
async def list_song_jobs(
    limit: Optional[int] = Query(default=10, ge=1, le=100),
    startAfter: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(authenticate_token),
):
    result = list_song_infer_jobs(auth.user_id, limit, startAfter)
    return send_success_response(200, "Song inference jobs retrieved", result)


@router.get("/jobs/{song_infer_job_id}", summary="Get song inference job detail")
async def song_job_detail(
    song_infer_job_id: str,
    auth: AuthContext = Depends(authenticate_token),
):
    try:
        result = get_song_infer_job_detail(song_infer_job_id, auth.user_id)
        return send_success_response(200, "Song inference job retrieved", result)
    except SongInferJobNotFoundError as exc:
        return send_error_response(404, "NOT_FOUND", str(exc))


@router.websocket("/jobs/{song_infer_job_id}/ws")
async def song_infer_progress_ws(websocket: WebSocket, song_infer_job_id: str):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        auth = verify_user_access_token(token)
        snapshot = get_song_infer_job_detail(song_infer_job_id, auth.user_id)
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
    await pubsub.subscribe(song_infer_channel(song_infer_job_id))
    safety_poll_interval = 30.0
    pubsub_timeout = 5.0
    last_safety_check = time.monotonic()
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=pubsub_timeout,
            )
            if message and message.get("type") == "message":
                payload = json.loads(message["data"])
                await websocket.send_json({"type": "progress", "data": payload})
                if payload.get("status") in {"succeeded", "failed"}:
                    await websocket.send_json({"type": "terminal", "data": payload})
                    break
                continue

            now = time.monotonic()
            if now - last_safety_check >= safety_poll_interval:
                last_safety_check = now
                latest = get_song_infer_job_detail(song_infer_job_id, auth.user_id)
                if latest.get("status") in {"succeeded", "failed"}:
                    await websocket.send_json({"type": "terminal", "data": latest})
                    break
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "data": {
                            "songInferJobId": song_infer_job_id,
                            "status": latest.get("status"),
                            "stage": latest.get("stage"),
                            "progress": latest.get("progress"),
                            "elapsedMs": latest.get("elapsedMs", 0),
                        },
                    }
                )
            else:
                await websocket.send_json(
                    {"type": "heartbeat", "data": {"songInferJobId": song_infer_job_id}}
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "data": {"message": str(exc)}})
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(song_infer_channel(song_infer_job_id))
        await pubsub.close()
        await redis_client.close()
