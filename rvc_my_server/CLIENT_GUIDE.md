# Hướng dẫn Client — Tạo và Theo dõi Training Job

Tài liệu này mô tả toàn bộ luồng mà client thực hiện để train một RVC model và theo dõi tiến trình.

**Base URL:** `http://<host>:<port>/dev/v1`  
**Auth:** Tất cả request cần header `Authorization: Bearer <accessToken>` (trừ khi ghi rõ khác)

---

## Mục lục

1. [Đăng ký / Đăng nhập](#1-đăng-ký--đăng-nhập)
2. [Upload audio để training](#2-upload-audio-để-training)
3. [Tạo training job](#3-tạo-training-job)
4. [Theo dõi tiến trình qua WebSocket](#4-theo-dõi-tiến-trình-qua-websocket)
5. [Polling HTTP (thay thế WebSocket)](#5-polling-http-thay-thế-websocket)
6. [Lấy model sau khi train xong](#6-lấy-model-sau-khi-train-xong)
7. [Vòng đời của job](#7-vòng-đời-của-job)
8. [Xử lý lỗi](#8-xử-lý-lỗi)

---

## 1. Đăng ký / Đăng nhập

### 1.1 Đăng ký tài khoản

```http
POST /dev/v1/auth-services/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your_password"
}
```

### 1.2 Đăng nhập

```http
POST /dev/v1/auth-services/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your_password"
}
```

**Response:**

```json
{
  "statusCode": 200,
  "data": {
    "accessToken": "eyJhbGci...",
    "refreshToken": "eyJhbGci..."
  }
}
```

Lưu `accessToken` vào bộ nhớ. Token này có TTL mặc định là `1 ngày`.

### 1.3 Refresh token

Khi `accessToken` hết hạn (server trả về `403`), dùng `refreshToken` để lấy token mới:

```http
POST /dev/v1/auth-services/refresh
Content-Type: application/json

{
  "refreshToken": "eyJhbGci..."
}
```

---

## 2. Upload audio để training

Quá trình upload gồm 2 bước: lấy signed URL → upload file trực tiếp lên Firebase Storage.

### Bước 2.1 — Xin signed upload URL

```http
POST /dev/v1/train-services/upload-urls
Authorization: Bearer <accessToken>
Content-Type: application/json

{
  "files": [
    { "fileName": "voice_01.wav", "contentType": "audio/wav" },
    { "fileName": "voice_02.wav", "contentType": "audio/wav" }
  ]
}
```

**Response:**

```json
{
  "statusCode": 200,
  "data": {
    "uploadSessionId": "session_1779267563260_abc123",
    "files": [
      {
        "audioUploadId": "audio_upload_1779267563260_uuid1",
        "fileName": "voice_01.wav",
        "objectPath": "train_uploads/user_123/audio_upload_..._voice_01.wav",
        "uploadUrl": "https://storage.googleapis.com/...",
        "method": "PUT",
        "headers": { "Content-Type": "audio/wav" },
        "expiresIn": 3600
      },
      {
        "audioUploadId": "audio_upload_1779267563260_uuid2",
        "fileName": "voice_02.wav",
        "uploadUrl": "https://storage.googleapis.com/...",
        "method": "PUT",
        "headers": { "Content-Type": "audio/wav" },
        "expiresIn": 3600
      }
    ]
  }
}
```

### Bước 2.2 — Upload file trực tiếp lên Storage

Với mỗi file trong danh sách trả về, client gửi PUT request thẳng đến `uploadUrl`:

```http
PUT <uploadUrl>
Content-Type: audio/wav

<binary file content>
```

> **Lưu ý:** URL có hiệu lực trong `expiresIn` giây (mặc định 3600s). Upload song song các file để tiết kiệm thời gian.

### Bước 2.3 — Ghi nhớ các `audioUploadId`

Lưu lại tất cả `audioUploadId` thu thập được. Chúng sẽ được dùng ở bước 3.

---

## 3. Tạo training job

Sau khi upload xong toàn bộ file âm thanh, gọi endpoint tạo job:

```http
POST /dev/v1/train-services/jobs
Authorization: Bearer <accessToken>
Content-Type: application/json

{
  "title": "Giọng nữ đọc truyện",
  "description": "Dataset thu trong phòng yên tĩnh",
  "audioUploadIds": [
    "audio_upload_1779267563260_uuid1",
    "audio_upload_1779267563260_uuid2"
  ],
  "sampleRate": "40k",
  "version": "v2",
  "ifF0": true,
  "f0Method": "rmvpe",
  "totalEpochs": 50,
  "saveEveryEpoch": 5,
  "batchSize": 4,
  "numProcesses": 4,
  "gpuDevicesTrain": "0",
  "gpusForRmvpe": "0",
  "speakerId": 0,
  "saveOnlyLatest": true,
  "cacheDatasetInGpu": false,
  "saveWeightsEveryEpoch": false,
  "pretrainedG": "",
  "pretrainedD": "",
  "preprocessPer": 3.7,
  "indexKmeansThreshold": 200000,
  "indexKmeansCenters": 10000,
  "indexBatchSize": 8192,
  "indexNprobe": 1
}
```

**Các tham số quan trọng:**

| Tham số | Kiểu | Mặc định | Mô tả |
|---------|------|----------|-------|
| `title` | string | bắt buộc | Tên model |
| `audioUploadIds` | string[] | bắt buộc | IDs của file đã upload |
| `sampleRate` | string | `"40k"` | Sample rate (`"32k"`, `"40k"`, `"48k"`) |
| `version` | string | `"v2"` | Phiên bản RVC (`"v1"`, `"v2"`) |
| `totalEpochs` | int | bắt buộc | Số epoch train (VD: 50-200) |
| `f0Method` | string | `"rmvpe"` | Thuật toán pitch (`"pm"`, `"harvest"`, `"crepe"`, `"rmvpe"`) |
| `batchSize` | int | `4` | Batch size (tăng nếu VRAM đủ) |
| `saveEveryEpoch` | int | `5` | Lưu checkpoint mỗi N epoch |

**Response (HTTP 202 Accepted):**

```json
{
  "statusCode": 202,
  "data": {
    "trainJobId": "train_job_1779267563260_xyz",
    "userId": "user_123",
    "title": "Giọng nữ đọc truyện",
    "status": "queued",
    "stage": "queued",
    "progress": 0,
    "elapsedMs": 0,
    "message": "Training job queued",
    "rvcModelId": "",
    "error": "",
    "createdAt": "2024-06-16T10:30:00Z"
  }
}
```

Lưu lại `trainJobId` để theo dõi job.

---

## 4. Theo dõi tiến trình qua WebSocket

WebSocket là cách **khuyến khích** để theo dõi job theo thời gian thực.

### Kết nối

```
WS ws://<host>:<port>/dev/v1/train-services/jobs/<trainJobId>/ws?token=<accessToken>
```

### Các loại message nhận được

#### `snapshot` — Trạng thái tức thì khi kết nối

Nhận ngay sau khi kết nối thành công. Đây là trạng thái hiện tại của job trong Firestore.

```json
{
  "type": "snapshot",
  "data": {
    "trainJobId": "train_job_...",
    "status": "queued",
    "stage": "queued",
    "progress": 0,
    "elapsedMs": 0,
    "message": "Training job queued",
    "rvcModelId": "",
    "error": ""
  }
}
```

#### `progress` — Cập nhật từ Celery worker

Gửi theo thời gian thực trong suốt quá trình train.

```json
{
  "type": "progress",
  "data": {
    "trainJobId": "train_job_...",
    "status": "running",
    "stage": "training",
    "progress": 42,
    "elapsedMs": 1800000,
    "message": "Epoch 21/50...",
    "rvcModelId": "",
    "error": ""
  }
}
```

**Các giá trị `stage` trong quá trình train:**

| Stage | Mô tả |
|-------|-------|
| `queued` | Đang chờ trong hàng đợi |
| `preprocess` | Đang tiền xử lý dataset |
| `extract` | Đang trích xuất feature F0 |
| `training` | Đang train model |
| `succeeded` | Hoàn thành |
| `failed` | Thất bại |

#### `heartbeat` — Kiểm tra định kỳ (mỗi 30 giây)

Server tự động poll Firestore mỗi 30 giây để đảm bảo không mất tin nhắn.

```json
{
  "type": "heartbeat",
  "data": {
    "trainJobId": "train_job_...",
    "status": "running",
    "stage": "training",
    "progress": 42,
    "elapsedMs": 1830000
  }
}
```

#### `terminal` — Kết thúc (thành công hoặc thất bại)

Nhận khi job kết thúc. Sau message này, client có thể đóng kết nối WebSocket.

```json
{
  "type": "terminal",
  "data": {
    "trainJobId": "train_job_...",
    "status": "succeeded",
    "stage": "succeeded",
    "progress": 100,
    "elapsedMs": 7200000,
    "message": "Training completed successfully",
    "rvcModelId": "rvc_1779267563260_abc",
    "error": "",
    "completedAt": "2024-06-16T12:30:00Z"
  }
}
```

Nếu `status = "failed"`, xem trường `error` để biết lý do.

#### `error` — Lỗi kết nối / xác thực

```json
{
  "type": "error",
  "data": { "message": "Token expired" }
}
```

### Ví dụ xử lý WebSocket (JavaScript)

```javascript
const ws = new WebSocket(
  `ws://localhost:8000/dev/v1/train-services/jobs/${trainJobId}/ws?token=${accessToken}`
);

ws.onmessage = (event) => {
  const { type, data } = JSON.parse(event.data);

  switch (type) {
    case 'snapshot':
      console.log('Trạng thái hiện tại:', data.status, data.stage);
      break;

    case 'progress':
      console.log(`Tiến trình: ${data.progress}% — ${data.message}`);
      updateProgressBar(data.progress);
      break;

    case 'heartbeat':
      // Server vẫn alive, không cần làm gì
      break;

    case 'terminal':
      if (data.status === 'succeeded') {
        console.log('Train xong! Model ID:', data.rvcModelId);
        fetchModelDetails(data.rvcModelId);
      } else {
        console.error('Train thất bại:', data.error);
      }
      ws.close();
      break;

    case 'error':
      console.error('Lỗi WebSocket:', data.message);
      ws.close();
      break;
  }
};

ws.onerror = (err) => console.error('Kết nối lỗi:', err);
```

---

## 5. Polling HTTP (thay thế WebSocket)

Nếu môi trường không hỗ trợ WebSocket, client có thể poll HTTP định kỳ.

### Lấy thông tin job

```http
GET /dev/v1/train-services/jobs/<trainJobId>
Authorization: Bearer <accessToken>
```

**Response:**

```json
{
  "statusCode": 200,
  "data": {
    "trainJobId": "train_job_...",
    "status": "running",
    "stage": "training",
    "progress": 42,
    "elapsedMs": 1800000,
    "message": "Epoch 21/50...",
    "rvcModelId": "",
    "error": "",
    "createdAt": "2024-06-16T10:30:00Z",
    "startedAt": "2024-06-16T10:31:00Z",
    "completedAt": ""
  }
}
```

### Chiến lược polling

```javascript
async function pollTrainJob(trainJobId, accessToken) {
  const POLL_INTERVAL_MS = 5000; // poll mỗi 5 giây

  while (true) {
    const res = await fetch(
      `/dev/v1/train-services/jobs/${trainJobId}`,
      { headers: { Authorization: `Bearer ${accessToken}` } }
    );
    const { data } = await res.json();

    console.log(`[${data.stage}] ${data.progress}% — ${data.message}`);

    if (data.status === 'succeeded') {
      console.log('Train xong! Model ID:', data.rvcModelId);
      break;
    }
    if (data.status === 'failed') {
      console.error('Train thất bại:', data.error);
      break;
    }

    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}
```

### Liệt kê tất cả training jobs

```http
GET /dev/v1/train-services/jobs?limit=10&status=active
Authorization: Bearer <accessToken>
```

**Query parameters:**

| Tham số | Mô tả |
|---------|-------|
| `limit` | Số lượng mỗi trang (1–100, mặc định 10) |
| `startAfter` | Cursor ID từ trang trước (phân trang) |
| `status` | Lọc theo trạng thái: `queued`, `running`, `succeeded`, `failed`, `active` (queued + running) |

---

## 6. Lấy model sau khi train xong

Khi job có `status = "succeeded"`, trường `rvcModelId` sẽ có giá trị. Dùng nó để lấy thông tin model:

```http
GET /dev/v1/train-services/models/<rvcModelId>
Authorization: Bearer <accessToken>
```

**Response:**

```json
{
  "statusCode": 200,
  "data": {
    "rvcModelId": "rvc_1779267563260_abc",
    "userId": "user_123",
    "title": "Giọng nữ đọc truyện",
    "description": "Dataset thu trong phòng yên tĩnh",
    "sampleRate": "40k",
    "version": "v2",
    "ifF0": true,
    "modelUrl": "https://storage.googleapis.com/...",
    "indexUrl": "https://storage.googleapis.com/...",
    "signedUrlExpiresIn": 3600,
    "trainJobId": "train_job_...",
    "createdAt": "2024-06-16T12:30:00Z"
  }
}
```

- `modelUrl`: Signed URL để tải file `.pth` (hết hạn sau `signedUrlExpiresIn` giây)
- `indexUrl`: Signed URL để tải file `.index`

---

## 7. Vòng đời của job

### Sơ đồ trạng thái

```
[Client tạo job]
        │
        ▼
    ┌────────┐
    │ queued │  ← Job chờ tài nguyên VRAM
    └────┬───┘
         │ Scheduler cấp VRAM
         ▼
    ┌─────────┐
    │ running │  ← Celery worker đang xử lý
    └────┬────┘
         │
    ┌────┴────────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌───────────┐                      ┌────────┐
│ succeeded │                      │ failed │
└───────────┘                      └────────┘
```

### Chi tiết các stage trong `running`

```
running/preprocess  →  running/extract  →  running/training  →  succeeded
```

### Hệ thống hàng đợi

- Jobs được xếp hàng FIFO theo thứ tự `createdAt`
- Scheduler kiểm tra tài nguyên VRAM mỗi 3 giây
- Khi một job hoàn thành, scheduler ngay lập tức kích hoạt job tiếp theo
- Mặc định: mỗi training job cần **4096 MB VRAM**

---

## 8. Xử lý lỗi

### Cấu trúc response lỗi

```json
{
  "statusCode": 400,
  "error": "VALIDATION_FAILED",
  "message": "audioUploadIds must not be empty"
}
```

### HTTP Status codes

| Code | Ý nghĩa | Cách xử lý |
|------|---------|------------|
| `202` | Job đã được xếp hàng thành công | Lưu `trainJobId`, bắt đầu theo dõi |
| `400` | Request không hợp lệ | Kiểm tra lại body/params |
| `401` | Thiếu hoặc sai token | Gửi lại với token đúng |
| `403` | Token hết hạn | Gọi `/auth-services/refresh` rồi thử lại |
| `404` | Không tìm thấy job/model | Kiểm tra lại ID |
| `500` | Lỗi server | Chờ rồi thử lại |

### Xử lý token hết hạn (403)

```javascript
async function fetchWithRefresh(url, options, tokens) {
  let res = await fetch(url, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${tokens.accessToken}` }
  });

  if (res.status === 403) {
    // Refresh token
    const refreshRes = await fetch('/dev/v1/auth-services/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken: tokens.refreshToken })
    });
    const { data } = await refreshRes.json();
    tokens.accessToken = data.accessToken;

    // Thử lại với token mới
    res = await fetch(url, {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${tokens.accessToken}` }
    });
  }

  return res;
}
```

---

## Tóm tắt luồng hoàn chỉnh

```
1. POST /auth-services/login
        → Lưu accessToken, refreshToken

2. POST /train-services/upload-urls
        → Lấy signed PUT URLs cho từng file

3. PUT <signedUrl>  (mỗi file)
        → Upload binary file lên Firebase Storage

4. POST /train-services/jobs
        → Tạo job, nhận trainJobId
        → HTTP 202, job ở trạng thái "queued"

5. WS  /train-services/jobs/<trainJobId>/ws
        → Nhận "snapshot" → "progress"... → "terminal"

6. GET /train-services/models/<rvcModelId>
        → Lấy modelUrl, indexUrl để tải model về
```
