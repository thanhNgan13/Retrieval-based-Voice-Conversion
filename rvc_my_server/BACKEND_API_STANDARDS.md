# Quy chuẩn thiết kế Backend & Response API

Tài liệu này mô tả **quy chuẩn thiết kế Backend (BE)** và **định dạng response** được rút ra từ codebase **Skin Sort Cloud Functions**. Áp dụng cho các module: `functions`, `function_api_management`, `check_subscription`, và các Cloud Function mới tương tự.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Quy ước URL & routing](#3-quy-ước-url--routing)
4. [Định dạng Response](#4-định-dạng-response)
5. [Mã HTTP & mã lỗi](#5-mã-http--mã-lỗi)
6. [Xác thực (Authentication)](#6-xác-thực-authentication)
7. [Phân trang (Pagination)](#7-phân-trang-pagination)
8. [Quy ước dữ liệu](#8-quy-ước-dữ-liệu)
9. [Luồng xử lý theo layer](#9-luồng-xử-lý-theo-layer)
10. [Swagger / API Docs](#10-swagger--api-docs)
11. [Biến môi trường & hằng số](#11-biến-môi-trường--hằng-số)
12. [Mẫu code tham chiếu](#12-mẫu-code-tham-chiếu)

---

## 1. Tổng quan kiến trúc

| Thành phần | Công nghệ |
|------------|-----------|
| Runtime | Node.js (CommonJS `require` / `module.exports`) |
| Framework HTTP | Express.js |
| Deploy | Firebase Cloud Functions (`firebase-functions`) |
| Database chính | Cloud Firestore |
| Auth | JWT (Bearer token) |
| API Docs | Swagger OpenAPI 3.0 (`swagger-jsdoc` + `swagger-ui-express`) |

**Mô hình phân lớp (Layered Architecture):**

```
Client
  → server.js (Express app, CORS, body parser, Swagger)
    → routes/*.js (định tuyến, middleware, Swagger JSDoc)
      → controllers/*.js (validate input, gọi service/model, trả response)
        → services/*.js (business logic phức tạp, tái sử dụng)
        → models/*.js (truy cập Firestore / schema chuẩn hóa)
      → utils/sendResponse.js (format JSON thống nhất)
```

**Nguyên tắc:**

- Controller **không** truy cập Firestore trực tiếp nếu đã có `model` hoặc `service`.
- Mọi response API **bắt buộc** qua `sendSuccessResponse` / `sendErrorResponse`.
- Secret, URL, version… lấy từ `src/utils/constant.js` và `.env`, **không hard-code** trong controller.

---

## 2. Cấu trúc thư mục

Mỗi Cloud Function codebase tuân theo cấu trúc sau:

```
<function_name>/
├── server.js                 # Entry: Express + export Firebase Function
├── package.json
├── .env                      # Biến môi trường (không commit)
└── src/
    ├── config/
    │   ├── firebase.js       # Khởi tạo Firestore, Storage, Auth
    │   └── swagger.js        # Cấu hình OpenAPI
    ├── controllers/          # Xử lý HTTP request/response
    ├── routes/
    │   ├── index.js          # Gắn prefix & mount các route module
    │   └── *Routes.js        # Route theo domain (auth, user, product…)
    ├── services/             # Business logic (tùy chọn)
    ├── models/               # Truy cập DB + chuẩn hóa document
    ├── middlewares/          # JWT, admin, multipart…
    ├── helpers/              # Email template, AI, upload ảnh…
    ├── utils/
    │   ├── constant.js       # Hằng số toàn app
    │   ├── sendResponse.js   # Template response JSON
    │   ├── validators.js     # Validate input
    │   ├── dataTransformUtils.js
    │   ├── cursorPagination.js
    │   └── idGenerator.js
    └── triggers/             # Firestore triggers (nếu có)
```

**Quy ước đặt tên file:**

| Loại | Pattern | Ví dụ |
|------|---------|-------|
| Controller | `*Controller.js` | `authController.js` |
| Route | `*Routes.js` | `userRoutes.js` |
| Service | `*Service.js` | `productService.js` |
| Model | `*Model.js` | `userModel.js` |
| Middleware | `*Middleware.js` | `authMiddleware.js` |

**Quy ước đặt tên trong code:**

- Class controller: `PascalCase` + suffix `Controller` → `FirebaseAuthController`, `PostController`
- Method handler: `camelCase`, gán bằng arrow function → `register = async (req, res) => {}`
- Biến / hàm utility: `camelCase`
- JSON response field: `camelCase` (Firestore snake_case được convert khi trả về client)
- Route path segment: `kebab-case` → `/auth-services`, `/api-keys-services`

---

## 3. Quy ước URL & routing

### 3.1. Cấu trúc URL

```
/{ENV_PREFIX}/{API_VERSION}/{service-name}/{endpoint}
```

| Thành phần | Giá trị mặc định | Mô tả |
|-----------|------------------|-------|
| `ENV_PREFIX` | `dev` | Tiền tố môi trường (`dev`, `staging`, `prod`…) |
| `API_VERSION` | `v1` | Phiên bản API |
| `service-name` | `*-services` | Nhóm API theo domain |

**Ví dụ (production):**

```
https://us-central1-skinsort-66179.cloudfunctions.net/api/dev/v1/auth-services/login
```

**Ví dụ (emulator local):**

```
http://127.0.0.1:5004/skinsort-66179/us-central1/api/dev/v1/auth-services/login
```

### 3.2. Danh sách service (module `functions`)

| Service path | Mô tả |
|--------------|-------|
| `/dev/v1/admin-services` | Quản trị |
| `/dev/v1/auth-services` | Đăng ký, đăng nhập, OAuth |
| `/dev/v1/user-services` | Hồ sơ người dùng |
| `/dev/v1/products-services` | Sản phẩm |
| `/dev/v1/post-services` | Bài viết |
| `/dev/v1/comment-services` | Bình luận |
| `/dev/v1/interaction-services` | Like, bookmark… |
| `/dev/v1/game-services` | Mini game |
| `/dev/v1/in-app-purchase-services` | IAP |
| `/dev/v1/report-services` | Báo cáo |
| `/dev/v1/startup-services` | Khởi động app |

### 3.3. Health check

Endpoint không nằm trong `v1`, dùng cho monitoring:

```
GET /{ENV_PREFIX}/health-check
```

**Response (không dùng `sendSuccessResponse`):**

```json
{
  "status": "OK",
  "environment": "dev",
  "version": "v1",
  "timestamp": "2026-05-19T10:00:00.000Z"
}
```

### 3.4. HTTP methods

| Method | Dùng cho |
|--------|----------|
| `GET` | Lấy dữ liệu |
| `POST` | Tạo mới |
| `PUT` / `PATCH` | Cập nhật |
| `DELETE` | Xóa |

### 3.5. Đăng ký route (`src/routes/index.js`)

```javascript
const { ENV_PREFIX, API_VERSION } = require("../utils/constant");
const authRoutes = require("./authRoutes");

module.exports = (app) => {
  const apiBasePath = `/${ENV_PREFIX}/${API_VERSION}`;
  app.use(`${apiBasePath}/auth-services`, authRoutes);
};
```

---

## 4. Định dạng Response

Mọi API JSON **phải** dùng helper trong `src/utils/sendResponse.js`.

### 4.1. Response thành công

**Cấu trúc:**

```json
{
  "statusCode": 200,
  "message": "Mô tả ngắn gọn kết quả",
  "data": {}
}
```

| Field | Kiểu | Bắt buộc | Mô tả |
|-------|------|----------|-------|
| `statusCode` | `number` | Có | Trùng HTTP status code |
| `message` | `string` | Có | Thông báo cho client/hiển thị |
| `data` | `any` | Không | Object, array, hoặc giá trị đơn. Mặc định `[]` nếu không truyền |

**Gọi trong code:**

```javascript
const { sendSuccessResponse } = require("../utils/sendResponse");

return sendSuccessResponse(res, 200, "User information", { userId, email });
return sendSuccessResponse(res, 201, "User created successfully");
```

**Ví dụ thực tế — đăng ký thành công:**

```json
{
  "statusCode": 201,
  "message": "User created successfully",
  "data": []
}
```

**Ví dụ — danh sách có phân trang:**

```json
{
  "statusCode": 200,
  "message": "Posts retrieved successfully",
  "data": {
    "paginatedItems": [
      { "id": "post_123", "content": "..." }
    ],
    "pagination": {
      "limit": 10,
      "hasNext": true,
      "nextCursor": "post_abc",
      "currentCount": 10
    }
  }
}
```

> **Lưu ý:** Swagger schema có field `timestamp` nhưng implementation hiện tại **chưa** tự động thêm `timestamp` vào body. Client có thể dùng HTTP header `Date` hoặc bổ sung sau nếu cần thống nhất với Swagger.

### 4.2. Response lỗi

**Cấu trúc:**

```json
{
  "statusCode": 400,
  "error": "VALIDATION_FAILED",
  "message": "All fields are required"
}
```

| Field | Kiểu | Bắt buộc | Mô tả |
|-------|------|----------|-------|
| `statusCode` | `number` | Có | Trùng HTTP status code |
| `error` | `string` | Có | Mã/loại lỗi (machine-readable) |
| `message` | `string` | Có | Chi tiết lỗi (human-readable) |

**Gọi trong code:**

```javascript
const { sendErrorResponse } = require("../utils/sendResponse");

return sendErrorResponse(
  res,
  400,
  "Validation Failed",
  "All fields are required"
);
```

**Ví dụ thực tế:**

```json
{
  "statusCode": 401,
  "error": "Access Denied",
  "message": "Access Token Required"
}
```

```json
{
  "statusCode": 403,
  "error": "Invalid Token",
  "message": "Access Token Invalid Or Expired"
}
```

### 4.3. So sánh Success vs Error

| | Success | Error |
|---|---------|-------|
| Field chính | `message` + `data` | `error` + `message` |
| Có `data` | Có (tùy chọn) | Không |
| Có `error` | Không | Có |

---

## 5. Mã HTTP & mã lỗi

### 5.1. HTTP Status Code

| Code | Khi nào dùng |
|------|----------------|
| `200` | GET/PUT/PATCH thành công |
| `201` | POST tạo resource thành công |
| `400` | Validation, dữ liệu không hợp lệ, business rule |
| `401` | Thiếu token / chưa đăng nhập |
| `403` | Token không hợp lệ hoặc hết hạn |
| `404` | Không tìm thấy resource |
| `500` | Lỗi server không mong đợi |

### 5.2. Quy ước giá trị `error` (gợi ý thống nhất)

Dự án đang dùng cả **Title Case** và **SCREAMING_SNAKE_CASE**. Khuyến nghị cho API mới:

| `error` | Ý nghĩa |
|---------|---------|
| `VALIDATION_FAILED` | Thiếu/sai tham số đầu vào |
| `BAD_REQUEST` | Request không hợp lệ |
| `UNAUTHORIZED` / `Access Denied` | 401 |
| `FORBIDDEN` / `Invalid Token` | 403 |
| `NOT_FOUND` | 404 |
| `INTERNAL_SERVER_ERROR` | 500 |

**Ví dụ đang dùng trong project:**

- `"Validation Failed"` — auth register
- `"VALIDATION_FAILED"` — `function_api_management`
- `"Access Denied"` / `"Invalid Token"` — middleware JWT
- `"Internal Server Error"` — catch block 500

---

## 6. Xác thực (Authentication)

### 6.1. Header

```
Authorization: Bearer <access_token>
```

### 6.2. Middleware (`src/middlewares/authMiddleware.js`)

| Middleware | Secret | Mục đích |
|------------|--------|----------|
| `authenticateToken` | `JWT_SECRET` | User thường |
| `authenticateTokenAdmin` | `ADMIN_JWT_SECRET` | Admin |
| `authenticateUserOrAdmin` | Admin hoặc User | Route cho cả user và admin |

**Sau khi xác thực**, gắn vào `req`:

```javascript
req.user      // payload JWT
req.userId    // userId từ token
req.isAdmin   // (authenticateUserOrAdmin) true/false
```

### 6.3. Thời hạn token (`constant.js`)

| Token | Thời hạn |
|-------|----------|
| Access token | `1d` |
| Refresh token | `30d` |

### 6.4. Gắn middleware vào route

```javascript
const { authenticateToken } = require("../middlewares/authMiddleware");

router.get("/profile", authenticateToken, userController.getProfile);
```

---

## 7. Phân trang (Pagination)

Dự án dùng **cursor-based pagination** (Firestore), utility: `src/utils/cursorPagination.js`.

### 7.1. Query parameters

| Param | Kiểu | Mặc định | Mô tả |
|-------|------|----------|-------|
| `limit` | `number` | `10` | Số item/trang (1–100) |
| `startAfter` | `string` | `null` | Document ID làm cursor |

### 7.2. Object `pagination` trong `data`

```json
{
  "limit": 10,
  "hasNext": true,
  "nextCursor": "document_id_cuối_trang",
  "currentCount": 10
}
```

### 7.3. Quy ước đặt tên trong `data`

| Pattern | Ví dụ endpoint |
|---------|----------------|
| `paginatedItems` + `pagination` | Posts, comments, admin users |
| `items` + `pagination` | Game categories/items |

Client gọi trang tiếp: truyền `startAfter={nextCursor}`.

---

## 8. Quy ước dữ liệu

### 8.1. Naming JSON

- **API request/response:** `camelCase`
- **Firestore document:** thường `snake_case` → convert khi trả client qua `convertFirestoreDocKeys()` / `deepSnakeToCamel()`

### 8.2. Timestamp

- Lưu Firestore: ISO string hoặc Firestore Timestamp
- Trả về client: ISO 8601 string (`convertTimestamp()`)

### 8.3. ID generator

Format: `{prefix}_{timestamp}_{uuid}`

```javascript
const { generateUserId } = require("../utils/idGenerator");
// → "user_1703123456789_550e8400-e29b-41d4-a716-446655440000"
```

### 8.4. Chuẩn hóa document (Model)

Model export các hàm:

- `prepare*Data()` — map request body → schema Firestore
- `add*ToFireStore()` / `get*FromFireStore()` / `update*InFireStore()` — CRUD

Ví dụ `prepareUserData(data, uid)` trong `userModel.js`.

---

## 9. Luồng xử lý theo layer

### 9.1. Controller — checklist

1. Validate `req.body` / `req.params` / `req.query` sớm → `400` + `sendErrorResponse`
2. Lấy `req.userId` từ middleware (nếu route protected)
3. Gọi `service` hoặc `model`
4. `sendSuccessResponse` với status phù hợp
5. `try/catch` → log `console.error` → `500` + `sendErrorResponse`

### 9.2. Mẫu controller chuẩn

```javascript
const {
  sendSuccessResponse,
  sendErrorResponse,
} = require("../utils/sendResponse");
const { getResourceById } = require("../services/exampleService");

class ExampleController {
  getById = async (req, res) => {
    try {
      const { id } = req.params;

      if (!id) {
        return sendErrorResponse(
          res,
          400,
          "VALIDATION_FAILED",
          "id is required"
        );
      }

      const item = await getResourceById(id);

      if (!item) {
        return sendErrorResponse(
          res,
          404,
          "NOT_FOUND",
          "Resource not found"
        );
      }

      return sendSuccessResponse(res, 200, "Resource retrieved successfully", item);
    } catch (error) {
      console.error("Error in getById:", error);
      return sendErrorResponse(
        res,
        500,
        "INTERNAL_SERVER_ERROR",
        error.message
      );
    }
  };
}

module.exports = new ExampleController();
```

### 9.3. Mẫu route chuẩn

```javascript
const express = require("express");
const exampleController = require("../controllers/exampleController");
const { authenticateToken } = require("../middlewares/authMiddleware");

const router = express.Router();

/**
 * @swagger
 * /example-services/{id}:
 *   get:
 *     tags: [Example]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/responses/SuccessResponse'
 */
router.get("/:id", authenticateToken, exampleController.getById);

module.exports = router;
```

---

## 10. Swagger / API Docs

| Endpoint | Mô tả |
|----------|-------|
| `/api-docs` | Swagger UI |
| `/api-docs.json` | OpenAPI JSON spec |
| `/` | Server info (dùng `sendSuccessResponse`) |

- Định nghĩa schema dùng chung: `#/components/schemas/SuccessResponse`, `ErrorResponse`
- Annotate route bằng JSDoc `@swagger` trong file `*Routes.js`
- Security: `bearerAuth` (JWT)

File cấu hình: `src/config/swagger.js`  
Scan paths: `./src/routes/*.js`, `./src/controllers/*.js`

---

## 11. Biến môi trường & hằng số

### 11.1. File `src/utils/constant.js`

Chứa: `API_VERSION`, `ENV_PREFIX`, `BASE_URL`, `JWT_SECRET`, token expiry, OAuth keys…

**Không** commit secret. Dùng `.env` + `process.env`.

### 11.2. Biến môi trường thường gặp

```
JWT_SECRET=
REFRESH_TOKEN_SECRET=
ADMIN_JWT_SECRET=
ADMIN_REFRESH_TOKEN_SECRET=
EMAIL_USER=
EMAIL_PASSWORD=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
FUNCTIONS_EMULATOR=true   # khi chạy local
```

---

## 12. Mẫu code tham chiếu

| File | Vai trò |
|------|---------|
| `functions/src/utils/sendResponse.js` | Template response |
| `functions/src/utils/constant.js` | Hằng số & URL |
| `functions/src/routes/index.js` | Mount routes |
| `functions/src/routes/authRoutes.js` | Route + Swagger đầy đủ |
| `functions/src/controllers/authController.js` | Auth flow mẫu |
| `functions/src/middlewares/authMiddleware.js` | JWT middleware |
| `functions/src/utils/cursorPagination.js` | Phân trang |
| `functions/src/config/swagger.js` | OpenAPI components |
| `function_api_management/` | Codebase mới, cùng pattern |

---

## Phụ lục: Checklist tạo API mới

- [ ] Thêm constant (nếu cần) vào `constant.js`
- [ ] Tạo `*Model.js` (Firestore) hoặc `*Service.js`
- [ ] Tạo `*Controller.js` dùng `sendSuccessResponse` / `sendErrorResponse`
- [ ] Tạo `*Routes.js` + JSDoc Swagger
- [ ] Đăng ký route trong `src/routes/index.js` với prefix `/{ENV_PREFIX}/{API_VERSION}/...`
- [ ] Gắn `authenticateToken` / `authenticateTokenAdmin` nếu cần bảo vệ
- [ ] Validate input trước khi gọi DB
- [ ] Test qua Swagger UI (`/api-docs`) hoặc emulator
- [ ] Response field dùng `camelCase`

---

*Tài liệu được sinh từ codebase Skin Sort Cloud Functions — cập nhật khi có thay đổi quy ước trong `sendResponse.js` hoặc `routes/index.js`.*
