import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import settings
from src.routes import register_routes
from src.utils.constant import API_BASE_PATH
from src.utils.send_response import send_error_response, send_success_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RVC My Server",
    description="Backend API for the RVC voice-conversion mobile app (phase 1: auth + user).",
    version="1.0.0",
    docs_url="/api-docs",
    openapi_url="/api-docs.json",
    redoc_url=None,
    swagger_ui_parameters={
        # Persist Authorize tokens in browser localStorage across page refresh.
        "persistAuthorization": True,
        # Keep request/response bodies expanded by default for easier debugging.
        "tryItOutEnabled": True,
        # Show operation tags collapsed for cleaner overview.
        "docExpansion": "none",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Exception handlers — normalize every error to the standard envelope.
# ------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail and "message" in detail:
        return send_error_response(exc.status_code, detail["error"], detail["message"])
    if exc.status_code == 401:
        return send_error_response(401, "Access Denied", str(detail) or "Access Token Required")
    if exc.status_code == 403:
        return send_error_response(403, "Invalid Token", str(detail) or "Access Token Invalid Or Expired")
    if exc.status_code == 404:
        return send_error_response(404, "NOT_FOUND", str(detail) or "Resource not found")
    return send_error_response(exc.status_code, "BAD_REQUEST", str(detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(str(part) for part in first.get("loc", [])[1:] or first.get("loc", []))
        message = f"{loc}: {first.get('msg')}" if loc else first.get("msg", "Invalid request")
    else:
        message = "Invalid request"
    return send_error_response(400, "VALIDATION_FAILED", message)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


# ------------------------------------------------------------------
# Root + health check
# ------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return send_success_response(
        200,
        "RVC My Server is running",
        {
            "environment": settings.ENV_PREFIX,
            "apiVersion": settings.API_VERSION,
            "basePath": API_BASE_PATH,
            "docs": "/api-docs",
        },
    )


@app.get(f"/{settings.ENV_PREFIX}/health-check", include_in_schema=False)
async def health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "OK",
            "environment": settings.ENV_PREFIX,
            "version": settings.API_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


register_routes(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
