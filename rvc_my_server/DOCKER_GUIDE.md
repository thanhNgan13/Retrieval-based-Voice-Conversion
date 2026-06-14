# Docker Guide — RVC My Server

## Kiến trúc

4 container chạy song song:

| Container | Image | Port | GPU | Vai trò |
|---|---|:-:|:-:|---|
| `redis` | `redis:7-alpine` | 6379 | ✗ | Message broker |
| `api-light` | `rvc-my-server:light` | **8000** | ✗ | Auth, user, train, model, admin |
| `infer` | `rvc-my-server:gpu` | **8001** | ✓ | Chỉ `/infer-services` (voice conversion) |
| `worker` | `rvc-my-server:gpu` | — | ✓ | Celery worker chạy training |

> `infer` và `worker` dùng **cùng 1 image GPU**, chỉ khác lệnh khởi động.

---

## Lần đầu tiên chạy

### 1. Chuẩn bị file môi trường

```bash
cd rvc_my_server

# Tạo .env từ mẫu rồi điền các biến JWT + Firebase
cp .env.example .env

# Đặt service account Firebase đúng chỗ
cp /path/to/serviceAccount.json src/config/serviceAccount.json
```

### 2. Kiểm tra GPU passthrough (bắt buộc nếu dùng infer/worker)

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Thấy bảng GPU → OK. Nếu lỗi → Docker chưa thấy GPU, cần bật WSL2 + NVIDIA driver trên Windows host.

### 3. Build image lần đầu

```bash
# Build cả 2 image: light (~3 phút) + gpu (~20-40 phút)
docker compose build
```

### 4. Khởi động

```bash
docker compose up -d
```

Sau khi chạy:
- Swagger api-light: http://localhost:8000/api-docs
- Swagger infer:     http://localhost:8001/api-docs
- Health check:      http://localhost:8000/dev/health-check

---

## Khi nào cần build lại

### Bắt buộc build lại

| Tình huống | Lệnh |
|---|---|
| Lần đầu chạy (chưa có image) | `docker compose build` |
| Thêm / xóa / đổi package trong `requirements-light.txt` | `docker compose build api-light` |
| Thêm / xóa / đổi package trong `requirements.txt` | `docker compose build infer` |
| Sửa `Dockerfile.light` | `docker compose build api-light` |
| Sửa `Dockerfile` | `docker compose build infer` |

Sau khi build xong, áp dụng bằng:

```bash
docker compose up -d
```

### Không cần build lại

| Tình huống | Cần làm |
|---|---|
| Sửa file `.py` (có `docker-compose.override.yml`) | Không làm gì — uvicorn tự reload |
| Sửa file `.py` (không có override) | `docker compose up -d --build <tên-service>` |
| Sửa `.env` | `docker compose up -d` |
| Sửa `docker-compose.yml` | `docker compose up -d` |
| File `.json`, `.yaml` config | Không làm gì — đọc trực tiếp từ volume |

---

## Development — sửa code không cần build lại

File `docker-compose.override.yml` (đã có sẵn trong thư mục này) mount code thật vào
container và bật `--reload` cho uvicorn. Docker Compose tự đọc file này khi chạy
`docker compose up`, không cần flag gì thêm.

**Khi sửa code Python:**

| Service | Hành vi |
|---|---|
| `api-light` | Tự reload ngay (~1 giây) |
| `infer` | Tự reload ngay (~1 giây) |
| `worker` | Phải restart thủ công: `docker compose restart worker` |

---

## Các lệnh thường dùng

```bash
# Xem log theo dõi
docker compose logs -f api-light
docker compose logs -f infer
docker compose logs -f worker

# Restart 1 service (ví dụ sau khi sửa code worker hoặc đổi .env)
docker compose restart worker
docker compose restart api-light

# Dừng tất cả container
docker compose down

# Dừng + xóa Redis volume (mất queue + cache Redis)
docker compose down -v

# Build lại toàn bộ không dùng cache (khi nghi ngờ cache cũ)
docker compose build --no-cache

# Vào shell trong container để debug
docker exec -it rvc-api-light bash
docker exec -it rvc-infer bash

# Kiểm tra GPU trong container infer
docker exec rvc-infer python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

---

## Lưu ý RTX 3050 4GB

`infer` và `worker` share cùng 1 GPU vật lý — VRAM 4 GB chỉ đủ cho 1 task tại 1 thời điểm:

- Đang demo **voice conversion** → không chạy training song song.
- Đang chạy **training** → không gọi `/infer-services/convert`.

Giải phóng VRAM giữa hai demo:

```bash
docker compose restart infer worker
```
