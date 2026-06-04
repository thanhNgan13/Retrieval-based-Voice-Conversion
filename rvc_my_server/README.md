# RVC My Server — Backend

Backend FastAPI cho ứng dụng mobile đổi giọng (Retrieval-based Voice Conversion).
Triển khai theo quy chuẩn trong [BACKEND_API_STANDARDS.md](BACKEND_API_STANDARDS.md),
port từ Node.js/Express + Firebase Cloud Functions sang **Python/FastAPI + Cloud Run**.

## Phase 1 (đang triển khai)
Backend FastAPI có auth, user, infer và training pipeline qua Celery/Redis.

- `/dev/v1/auth-services/register`, `/login`, `/refresh`, `/logout`
- `/dev/v1/user-services/profile` (GET, PUT, DELETE), `/:userId` (GET)
- `/dev/health-check`
- Swagger UI: `/api-docs`

## Chạy local

### Chạy native không Docker: API + training

Các lệnh dưới đây chạy trực tiếp trên Windows/PowerShell, không dùng Docker.
Chạy trong thư mục `rvc_my_server/`.

#### 1. Setup lần đầu

```powershell
cd D:\DUT_ITF\Semester_10th\do_an_tot_nghiep\example_training_voice\Retrieval-based-Voice-Conversion-WebUI\rvc_my_server

python -m venv .venv
.\.venv\Scripts\Activate.ps1

# fairseq 0.12.2 cần pip < 24.1.
python -m pip install -U "pip>=23.2,<24.1"

# Auto-detect GPU/CPU, cài torch và toàn bộ dependency RVC/API.
python install_deps.py
```

Nếu muốn ép mode cài đặt:

```powershell
# Ép CUDA cụ thể, ví dụ CUDA 12.4
python install_deps.py --cuda 12.4

# Ép CPU-only
python install_deps.py --cpu
```

#### 2. Tạo file `.env`

Tạo `.env` trong `rvc_my_server/`:

```env
ENV_PREFIX=dev
API_VERSION=v1
PORT=8000

GOOGLE_APPLICATION_CREDENTIALS=./serviceAccount.json
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_STORAGE_BUCKET=your_bucket.appspot.com

JWT_SECRET=change_me
REFRESH_TOKEN_SECRET=change_me
ADMIN_JWT_SECRET=change_me
ADMIN_REFRESH_TOKEN_SECRET=change_me

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin

ASSETS_DIR=./assets
INFER_CACHE_DIR=./cache
TRAIN_CACHE_DIR=./cache/train_jobs

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

`GOOGLE_APPLICATION_CREDENTIALS` trỏ tới file service account Firebase, ví dụ
`./serviceAccount.json` nếu file nằm ngay trong `rvc_my_server/`.

#### 3. Chuẩn bị assets

Chạy API trước, login admin trong Swagger, rồi gọi các endpoint setup asset:

```text
POST /dev/v1/admin-services/setup-assets
POST /dev/v1/admin-services/setup-training-assets
POST /dev/v1/admin-services/setup-uvr5-assets
```

Hoặc kiểm tra trạng thái:

```text
GET /dev/v1/admin-services/assets-status
GET /dev/v1/admin-services/training-assets-status
GET /dev/v1/admin-services/uvr5-assets-status
```

Training cần đủ:

```text
assets/hubert/hubert_base.pt
assets/rmvpe/rmvpe.pt
assets/pretrained/
assets/pretrained_v2/
assets/weights/
logs/mute/
```

Nếu `logs/mute` thiếu, copy thủ công từ repo RVC đầy đủ hoặc `rvc_standalone/logs/mute`.

#### 4. Chạy API + training bằng 3 terminal

Terminal 1: Redis

```powershell
cd D:\DUT_ITF\Semester_10th\do_an_tot_nghiep\example_training_voice\Retrieval-based-Voice-Conversion-WebUI\rvc_my_server
redis-server
```

Terminal 2: Celery worker chạy training

```powershell
cd D:\DUT_ITF\Semester_10th\do_an_tot_nghiep\example_training_voice\Retrieval-based-Voice-Conversion-WebUI\rvc_my_server
.\.venv\Scripts\Activate.ps1

celery -A src.config.celery_app.celery_app worker --loglevel=info --pool=solo --concurrency=1
```

Terminal 3: FastAPI

```powershell
cd D:\DUT_ITF\Semester_10th\do_an_tot_nghiep\example_training_voice\Retrieval-based-Voice-Conversion-WebUI\rvc_my_server
.\.venv\Scripts\Activate.ps1

uvicorn main:app --reload --port 8000
```

Sau khi chạy:

```text
Swagger:      http://127.0.0.1:8000/api-docs
Health check: http://127.0.0.1:8000/dev/health-check
API base:     http://127.0.0.1:8000/dev/v1
WebSocket:    ws://127.0.0.1:8000/dev/v1/train-services/jobs/{trainJobId}/ws?token=<accessToken>
```

#### 5. Luồng training private model

1. `POST /dev/v1/train-services/upload-urls`
2. Client `PUT` audio binary lên từng `uploadUrl`
3. `POST /dev/v1/train-services/jobs`
4. Theo dõi progress bằng WebSocket hoặc `GET /dev/v1/train-services/jobs/{trainJobId}`
5. Khi job `succeeded`, dùng `rvcModelId` để gọi `/dev/v1/infer-services/convert`

### 1. Cài Docker

Cài Docker Desktop. Trên Windows nên bật WSL2 backend.

### 2. Cấu hình Firebase

- Vào Firebase Console → Project Settings → Service Accounts → Generate new private key.
- Lưu file JSON vào thư mục này (ví dụ `serviceAccount.json`).
- Copy `.env.example` thành `.env`, sửa `GOOGLE_APPLICATION_CREDENTIALS`,
  `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, và 4 secret JWT.

Ví dụ nếu file service account nằm ngay trong `rvc_my_server/`:

```text
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccount.json
```

### 3. Chạy Docker local với NVIDIA GPU (4 service, kiến trúc production-ready)

Stack được tách thành **4 container** để CPU workload không tốn GPU. Layout
này giống hệt khi deploy Cloud Run — mỗi service map 1-1 với 1 Cloud Run
service (xem mục Cloud Run bên dưới).

| Service | Image | Port host | GPU | Routes / Vai trò |
|---|---|:-:|:-:|---|
| `redis` | `redis:7-alpine` (~30 MB) | 6379 | ✗ | Celery broker + Pub/Sub progress |
| `api-light` | `rvc-my-server:light` (~500 MB) | **8000** | ✗ | `/auth-services`, `/user-services`, `/rvc-model-services`, `/train-services`, `/admin-services` |
| `infer` | `rvc-my-server:gpu` (~9 GB) | **8001** | ✓ | CHỈ `/infer-services/*` (voice conversion + UVR5 separation) |
| `worker` | `rvc-my-server:gpu` (cùng image với infer) | — | ✓ | Celery worker chạy training pipeline |

Routes được bật/tắt theo env var `APP_ROLE` (`light` / `infer` / `all`). Cùng
1 code base, 2 image (light cho CPU, gpu cho infer + worker).

#### Client/mobile cần biết 2 base URL

```text
# Local
API_BASE   = http://localhost:8000/dev/v1   # auth, user, train, model, admin
INFER_BASE = http://localhost:8001/dev/v1   # convert

# Production (Cloud Run)
API_BASE   = https://api-light-xxx.run.app/dev/v1
INFER_BASE = https://infer-xxx.run.app/dev/v1
```

WebSocket train progress hosted trên api-light:
`ws://localhost:8000/dev/v1/train-services/jobs/{trainJobId}/ws?token=<accessToken>`.

#### Yêu cầu host

- **Windows 11** (hoặc Windows 10 21H2+) với WSL2.
- **Docker Desktop** — Settings → General → bật "Use WSL2 based engine".
- **NVIDIA driver** ≥ 525 trên Windows host (KHÔNG cài driver trong WSL).
- Test GPU passthrough đã ok chưa:
  ```powershell
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
  ```
  Nếu thấy bảng GPU = OK. Nếu fail → Docker chưa thấy GPU.

#### Build + chạy

```powershell
# Build cả 2 image (light ~3 phút, gpu ~20-40 phút lần đầu)
docker compose build

# Start 4 service ở background
docker compose up -d

# Xem log từng service
docker compose logs -f api-light
docker compose logs -f infer
docker compose logs -f worker
```

Sau khi container chạy:

| URL | Service | Mô tả |
|---|---|---|
| `http://127.0.0.1:8000/api-docs` | api-light | Swagger UI cho auth/user/train/model/admin |
| `http://127.0.0.1:8000/dev/health-check` | api-light | Health check |
| `http://127.0.0.1:8001/api-docs` | infer | Swagger UI cho /infer-services |
| `http://127.0.0.1:8001/dev/health-check` | infer | Health check |
| `localhost:6379` | redis | Broker (chỉ debug) |

#### Xác minh GPU trong container infer

```
GET http://127.0.0.1:8001/dev/v1/admin-services/torch-status
```

Đợi — `admin-services` chạy trên api-light, không phải infer. **Để verify GPU
trong infer container**, gắn shell vào nó:

```powershell
docker exec rvc-infer python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"
```

Hoặc xem log infer khi gọi `/infer-services/convert` lần đầu — sẽ thấy
`VC engine ready (device=cuda:0, is_half=True)`.

Trên api-light, gọi `/admin-services/torch-status` sẽ trả `torch.installed: false` —
**đúng theo thiết kế** (api-light không có torch).

#### Lưu ý GPU yếu (RTX 3050 4GB)

Cả `infer` và `worker` share 1 GPU vật lý. VRAM 4 GB chỉ đủ cho 1 process tại
1 thời điểm:

- Khi demo **infer** → đừng chạy job train song song.
- Khi demo **train** → đừng gọi `/infer-services/convert`.

Nếu cần restart engine để giải phóng VRAM giữa hai demo:

```powershell
docker compose restart infer worker
```

Trên Cloud Run, mỗi service có GPU riêng (L4 24GB) — không có vấn đề này.

#### Stop / cleanup

```powershell
docker compose down              # stop + remove containers
docker compose down -v           # ... + wipe Redis volume
docker compose restart worker    # restart 1 service
docker compose build --no-cache api-light infer  # full rebuild
```

#### Volumes — file persist giữa các lần restart

Cả 3 service api-light/infer/worker mount chung 3 thứ:

| Host | Container | Mục đích |
|---|---|---|
| `./serviceAccount.json` | `/app/serviceAccount.json` (RO) | Firebase auth |
| `./assets/` | `/app/assets/` | Hubert, RMVPE, pretrained G/D, logs/mute |
| `./cache/` | `/app/cache/` | `.pth` user-model + infer outputs + train workspace |

→ Tải Hubert/RMVPE 1 lần qua `POST /admin-services/setup-assets` ở api-light,
file ghi vào `./assets/` trên host → infer container đọc được ngay (cùng volume).

Với chức năng tách bài hát thành vocal/instrumental, tải UVR5 weights 1 lần qua:

```text
POST /dev/v1/admin-services/setup-uvr5-assets
GET  /dev/v1/admin-services/uvr5-assets-status
```

Sau đó gọi trên infer service:

```text
GET  /dev/v1/infer-services/separation-models
POST /dev/v1/infer-services/separate
```

`POST /infer-services/separate` nhận multipart form gồm `audio`, tuỳ chọn
`modelName=HP2_all_vocals`, `agg=10`, `outputFormat=wav`, và trả về
`outputs.vocal.url` + `outputs.instrumental.url`.

### Deploy Cloud Run từ kiến trúc này

Mỗi service trong `docker-compose.yml` map 1-1 với 1 Cloud Run service:

| Local service | Cloud Run | Cấu hình đề xuất |
|---|---|---|
| `redis` | **Memorystore Redis** (managed) | 1 GB Basic, ~$45/tháng |
| `api-light` | Cloud Run service (CPU) | `min-instances=1` để không cold-start auth, ~$17/tháng |
| `infer` | Cloud Run service (GPU L4) | `min-instances=0` scale-to-zero, ~$0.50/h khi dùng |
| `worker` | Cloud Run Job hoặc Cloud Run service (GPU L4) | `min-instances=0`, trigger qua Cloud Tasks hoặc poll Redis |

Mobile chỉ cần đổi 2 hằng số:
```
API_BASE   = https://api-light-xxx.run.app
INFER_BASE = https://infer-xxx.run.app
```

Code app không đổi gì giữa local và production. Đó là toàn bộ giá trị của việc
tách 4 service ngay từ đầu.

### 4. Native Python local, chỉ dùng khi cần debug ngoài Docker

PowerShell (Windows):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# fairseq 0.12.2 cần pip < 24.1 (vì omegaconf metadata cũ).
python -m pip install -U "pip>=23.2,<24.1"

# Auto-detect NVIDIA GPU và cài torch + toàn bộ requirements.
# Nếu máy có CUDA driver → tự chọn wheel cu118/cu121/cu124 phù hợp.
# Nếu không có GPU → fallback CPU.
python install_deps.py

# (Tùy chọn) ép GPU/CPU rõ ràng:
# python install_deps.py --cuda 12.4
# python install_deps.py --cpu
```

### 5. Chạy server riêng lẻ

```powershell
uvicorn main:app --reload --port 8000
```

- API base: `http://127.0.0.1:8000/dev/v1`
- Swagger: `http://127.0.0.1:8000/api-docs`
- Health: `http://127.0.0.1:8000/dev/health-check`

### 6. Chạy Redis + Celery worker cho training theo từng terminal

Training RVC chạy qua Celery, progress realtime publish qua Redis và WebSocket.
Trên Windows nên dùng `--pool=solo` để tránh lỗi multiprocessing/fork.

```powershell
# Terminal 1: Redis server
redis-server

# Terminal 2: Celery worker, chạy trong thư mục rvc_my_server
celery -A src.config.celery_app.celery_app worker --loglevel=info --pool=solo --concurrency=1

# Terminal 3: FastAPI
uvicorn main:app --reload --port 8000
```

Luồng train private model:

1. `POST /dev/v1/train-services/upload-urls` để lấy signed PUT URL.
2. Client PUT audio lên Storage bằng URL đó.
3. `POST /dev/v1/train-services/jobs` với `audioObjectPaths`.
4. Subscribe WebSocket: `/dev/v1/train-services/jobs/{trainJobId}/ws?token=<accessToken>`.
5. Khi job `succeeded`, model nằm trong `users/{userId}/rvc_models/{rvcModelId}` và có thể dùng ngay với `/infer-services/convert`.

Server train cần đủ asset RVC:

```text
assets/hubert/hubert_base.pt
assets/rmvpe/rmvpe.pt
assets/pretrained/
assets/pretrained_v2/
assets/weights/
logs/mute/
```

## Deploy Cloud Run

Xem [CLOUD_RUN.md](CLOUD_RUN.md). Cloud Run production không dùng
`run_all.ps1`; API, Redis và Celery worker nên được tách thành Cloud Run service,
managed Redis và Cloud Run worker pool.

## Cấu trúc thư mục

```
rvc_my_server/
├── main.py                  # FastAPI app + Uvicorn entry
├── requirements.txt
├── .env.example
└── src/
    ├── config/              # firebase.py, settings.py
    ├── controllers/         # auth_controller.py, user_controller.py
    ├── routes/              # auth_routes.py, user_routes.py, __init__.py (mount)
    ├── services/            # auth_service.py, user_service.py
    ├── models/              # user_model.py (Firestore CRUD)
    ├── middlewares/         # auth_middleware.py (JWT)
    ├── schemas/             # Pydantic request/response models
    └── utils/               # send_response, constant, id_generator, ...
```

## Quy ước response

Success:
```json
{ "statusCode": 200, "message": "...", "data": {} }
```

Error:
```json
{ "statusCode": 400, "error": "VALIDATION_FAILED", "message": "..." }
```

Tất cả endpoint phải dùng `send_success_response` / `send_error_response`
trong [src/utils/send_response.py](src/utils/send_response.py).
