# Công nghệ Backend - RVC Voice Conversion Server

## Tổng quan kiến trúc

Hệ thống backend được xây dựng theo kiến trúc **microservice phân tách CPU/GPU**, sử dụng container Docker để tách biệt tải xử lý nhẹ (API) khỏi tải nặng (ML inference/training). Giao tiếp nội bộ qua Redis, dữ liệu lưu trên Firestore, tệp âm thanh trên Firebase Storage.

```
Client
  │
  ├─► api-light (CPU, port 8000)  ─── Firestore ──► Google Cloud
  │       │                                          Storage
  │       │── Redis ──► worker (GPU, Celery)
  │
  └─► infer (GPU, port 8001)
```

---

## 1. Web Framework & API Server

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **FastAPI** | 0.115.4 | Framework HTTP bất đồng bộ chính |
| **Uvicorn** | 0.32.0 | ASGI server |
| **Pydantic** | 2.9.2 | Validate dữ liệu request/response |
| **pydantic-settings** | 2.6.1 | Quản lý cấu hình từ `.env` |
| **python-multipart** | 0.0.12 | Xử lý file upload |

**Đặc điểm:**
- RESTful API với JSON thuần
- Swagger UI tự động tại `/api-docs`
- CORS bật cho mọi origin
- Async/await toàn bộ request pipeline

**9 nhóm API route:**

| Route prefix | Chức năng |
|---|---|
| `/dev/v1/auth-services` | Đăng ký, đăng nhập, refresh token |
| `/dev/v1/user-services` | Quản lý hồ sơ người dùng |
| `/dev/v1/rvc-model-services` | Metadata mô hình RVC |
| `/dev/v1/train-services` | Quản lý job training |
| `/dev/v1/song-infer-services` | Quản lý job voice conversion |
| `/dev/v1/infer-services` | Inference GPU trực tiếp |
| `/dev/v1/separation-services` | Tách nhạc/giọng |
| `/dev/v1/admin-services` | Quản trị hệ thống |

---

## 2. Xác thực & Phân quyền

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **PyJWT** | 2.9.0 | Tạo và xác thực JWT token |
| **bcrypt** | 4.2.0 | Hash mật khẩu |

**Cơ chế:**
- JWT với thuật toán **HS256**
- **Access token**: thời hạn 1 ngày
- **Refresh token**: thời hạn 30 ngày
- Hai luồng xác thực riêng biệt: `user` và `admin`
- HTTPBearer middleware kiểm tra header `Authorization`

```
bearerAuth       → JWT secret người dùng
bearerAdminAuth  → JWT secret admin riêng biệt
```

---

## 3. Cơ sở dữ liệu - Google Cloud Firestore

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **firebase-admin** | 6.5.0 | SDK quản trị Firebase |
| **google-cloud-firestore** | 2.19.0 | Client Firestore |

**Các collection chính:**

| Collection | Nội dung |
|---|---|
| `users` | Hồ sơ người dùng |
| `rvc_models` | Metadata mô hình RVC công khai |
| `rvc_train_jobs` | Lịch sử job training |
| `rvc_song_infer_jobs` | Lịch sử job voice conversion |
| `list_cover` | Danh sách cover |
| `rvc_audio_uploads` | Theo dõi file upload |
| `playlists` | Playlist người dùng |

**Sub-collection (per-user):**
- `users/{userId}/rvc_models` — Mô hình riêng tư
- `users/{userId}/recent_songs` — Bài hát gần đây
- `users/{userId}/recent_models` — Mô hình vừa dùng
- `playlists/{playlistId}/songs` — Bài trong playlist

**Đặc điểm truy vấn:**
- Cursor-based pagination (Firestore native)
- Realtime listeners theo dõi tiến độ job
- Hỗ trợ **Firestore Emulator** cho môi trường dev

---

## 4. Lưu trữ tệp - Firebase Storage

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **google-cloud-storage** | 2.18.2 | Lưu trữ file âm thanh và mô hình |

**Cấu trúc bucket:**

| Thư mục | Nội dung |
|---|---|
| `public_rvc_model/` | Mô hình RVC công khai |
| `user_rvc_model/` | Mô hình người dùng tự train |
| `train_uploads/` | File âm thanh dùng để train |
| `song_infer_inputs/` | File đầu vào voice conversion |
| `song_infer_outputs/` | File kết quả voice conversion |

**Tính năng:** Signed URL thời hạn 3600 giây cho phép client upload/download trực tiếp.

---

## 5. Hàng đợi tác vụ - Redis & Celery

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **Redis** | 7.0 (Alpine) | Message broker + pub/sub |
| **Celery** | 5.4.0 | Distributed task queue |
| **redis** (Python) | 5.2.0 | Client Redis đồng bộ và bất đồng bộ |

**Các tác vụ Celery:**

| Task | Mô tả |
|---|---|
| `train_rvc_model_task` | Training mô hình RVC (chạy nền, mất nhiều giờ) |
| `infer_song_cover_task` | Voice conversion một bài hát |

**Cấu hình Celery quan trọng:**
```python
task_track_started = True        # Theo dõi task đang chạy
worker_prefetch_multiplier = 1   # Không prefetch, để scheduler kiểm soát
task_acks_late = True            # Acknowledge sau khi hoàn thành
```

---

## 6. Job Scheduler & Quản lý tài nguyên GPU

**Job Scheduler** (`/src/services/job_scheduler.py`):
- Chạy như asyncio background task trong FastAPI lifespan
- Poll Firestore mỗi **3 giây** tìm job đang chờ
- Phân bổ VRAM trước khi dispatch, tránh OOM
- Redis pub/sub để nhận signal khi job hoàn thành
- Dùng Redis `WATCH/MULTI/EXEC` tránh race condition
- Tự phục hồi sau crash (cleanup stale allocation)

**Resource Manager** (`/src/services/resource_manager.py`):
- Theo dõi VRAM allocation bằng Redis
- Giao dịch nguyên tử (atomic) khi cấp/thu hồi VRAM
- Ngân sách VRAM mặc định theo GPU thực tế (fallback 8 GB)

| Loại job | VRAM budget |
|---|---|
| Training | 4096 MB |
| Inference | 3072 MB |

---

## 7. Realtime - WebSocket

**Endpoints WebSocket:**
- `/train-services/jobs/{trainJobId}/ws`
- `/song-infer-services/jobs/{songInferJobId}/ws`

**Xác thực:** Token JWT qua query parameter

**Thông tin realtime broadcast:**

| Trường | Ý nghĩa |
|---|---|
| `status` | `queued / running / succeeded / failed` |
| `stage` | Giai đoạn hiện tại (preprocessing, training, ...) |
| `progress` | Phần trăm hoàn thành (0–100) |
| `elapsed_ms` | Thời gian đã chạy |
| `message` | Mô tả trạng thái |
| `error` | Chi tiết lỗi nếu thất bại |

---

## 8. Container hóa - Docker

### Hai Docker Image

**GPU Image** (`Dockerfile`)
- Base: `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`
- Kích thước: ~9–10 GB
- Chứa toàn bộ ML stack (PyTorch CUDA, fairseq, FAISS, ...)
- Dùng cho service `infer` và `worker`

**Light Image** (`Dockerfile.light`)
- Base: `python:3.10-slim-bookworm`
- Kích thước: ~500 MB
- Chỉ chứa web dependencies, không có ML
- Dùng cho service `api-light`

### Docker Compose - 4 service

| Service | Image | Port | Vai trò |
|---|---|---|---|
| `redis` | redis:7.0-alpine | 6379 | Message broker |
| `api-light` | Light image | 8000 | API server chính (CPU) |
| `infer` | GPU image | 8001 | Inference endpoint (GPU) |
| `worker` | GPU image | — | Celery worker nền (GPU) |

**Phân tách vai trò qua biến môi trường `APP_ROLE`:**

| Giá trị | Service nào dùng | Route được bật |
|---|---|---|
| `light` | api-light | Tất cả trừ `/infer-services`, `/separation-services` |
| `infer` | infer | Chỉ `/infer-services`, `/separation-services` |
| `all` | Dev all-in-one | Toàn bộ |
| `worker` | Celery worker | Không có HTTP |

---

## 9. Stack ML - RVC Voice Conversion

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| **PyTorch** | 2.6.0 + CUDA 12.4 | Deep learning framework |
| **torchaudio** | 2.6.0 | Xử lý âm thanh |
| **fairseq** | 0.12.2 | Kiến trúc mô hình RVC (HuBERT) |
| **faiss-cpu** | 1.7.3 | Tìm kiếm vector similarity |
| **librosa** | 0.9.1 | Feature extraction âm thanh |
| **soundfile** | ≥0.12.1 | Đọc/ghi WAV |
| **pydub** | ≥0.25.1 | Chỉnh sửa âm thanh |
| **ffmpeg-python** | ≥0.2.0 | Chuyển đổi định dạng media |
| **pedalboard** | ≥0.9.16 | Audio effects |
| **torchcrepe** | 0.0.20 | Trích xuất F0 (pitch) bằng CREPE |
| **torchfcpe** | latest | Trích xuất F0 bằng FCPE |
| **praat-parselmouth** | ≥0.4.2 | Trích xuất F0 bằng Praat |
| **pyworld** | 0.3.2 | Trích xuất F0 bằng WORLD vocoder |
| **onnxruntime** | latest | Chạy mô hình ONNX |

**Tách nhạc (UVR5):** MDXNet models tách giọng hát khỏi nhạc nền.

---

## 10. Kiến trúc phân lớp

```
HTTP Request
    │
    ▼
Routes  (/src/routes/)          ← FastAPI routers, validate schema
    │
    ▼
Controllers  (/src/controllers/) ← Điều phối, chuyển lỗi thành HTTP response
    │
    ▼
Services  (/src/services/)       ← Business logic, xử lý RVC
    │
    ▼
Models  (/src/models/)           ← Truy vấn Firestore trực tiếp (không ORM)
    │
    ▼
Google Firestore / Firebase Storage
```

**Schemas** (`/src/schemas/`) — Pydantic models cho request/response

**Config** (`/src/config/`) — Khởi tạo settings, Celery, Firebase

**Tasks** (`/src/tasks/`) — Định nghĩa Celery task

**Utils** (`/src/utils/`) — Pagination, response envelope, constants

---

## 11. Ghi log & Theo dõi

- Python `logging` chuẩn, level INFO
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Ghi ra thư mục `./logs/`
- Endpoint health check: `GET /health-check`
- Redis health check trong Docker Compose

---

## 12. Tóm tắt stack

```
┌─────────────────────────────────────────────────────────┐
│                    BACKEND TECHNOLOGIES                 │
├────────────────────┬────────────────────────────────────┤
│ Web Framework      │ FastAPI + Uvicorn (async)           │
│ Data Validation    │ Pydantic v2                         │
│ Authentication     │ JWT (PyJWT) + bcrypt                │
│ Database           │ Google Cloud Firestore (NoSQL)      │
│ File Storage       │ Firebase Storage (GCS)              │
│ Message Broker     │ Redis 7.0                           │
│ Task Queue         │ Celery 5.4                          │
│ Realtime           │ WebSocket (FastAPI native)          │
│ ML Framework       │ PyTorch 2.6 + CUDA 12.4             │
│ RVC Core           │ fairseq + FAISS                     │
│ Audio Processing   │ librosa + ffmpeg + pedalboard       │
│ Pitch Extraction   │ CREPE / FCPE / Praat / WORLD        │
│ Containerization   │ Docker + Docker Compose             │
│ Language           │ Python 3.10                         │
└────────────────────┴────────────────────────────────────┘
```
