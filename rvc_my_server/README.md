# RVC My Server — Backend

Backend FastAPI cho ứng dụng mobile đổi giọng (Retrieval-based Voice Conversion).
Triển khai theo quy chuẩn trong [BACKEND_API_STANDARDS.md](BACKEND_API_STANDARDS.md),
port từ Node.js/Express + Firebase Cloud Functions sang **Python/FastAPI + Cloud Run**.

## Phase 1 (đang triển khai)
Chỉ auth + user. Chưa có infer/training. Chưa có Docker.

- `/dev/v1/auth-services/register`, `/login`, `/refresh`, `/logout`
- `/dev/v1/user-services/profile` (GET, PUT, DELETE), `/:userId` (GET)
- `/dev/health-check`
- Swagger UI: `/api-docs`

## Chạy local

### 1. Cài đặt Python 3.10+

### 2. Tạo virtualenv & cài dependency

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

Sau khi cài xong, có thể verify GPU bằng API `GET /admin-services/torch-status` (xem mục Endpoint).

### 3. Cấu hình Firebase

- Vào Firebase Console → Project Settings → Service Accounts → Generate new private key.
- Lưu file JSON vào thư mục này (ví dụ `serviceAccount.json`).
- Copy `.env.example` thành `.env`, sửa `GOOGLE_APPLICATION_CREDENTIALS`,
  `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, và 4 secret JWT.

### 4. Chạy server

```powershell
uvicorn main:app --reload --port 8000
```

- API base: `http://127.0.0.1:8000/dev/v1`
- Swagger: `http://127.0.0.1:8000/api-docs`
- Health: `http://127.0.0.1:8000/dev/health-check`

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
