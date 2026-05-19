from typing import Any, Optional

from fastapi.responses import JSONResponse


def send_success_response(
    status_code: int,
    message: str,
    data: Optional[Any] = None,
) -> JSONResponse:
    body = {
        "statusCode": status_code,
        "message": message,
        "data": data if data is not None else [],
    }
    return JSONResponse(status_code=status_code, content=body)


def send_error_response(
    status_code: int,
    error: str,
    message: str,
) -> JSONResponse:
    body = {
        "statusCode": status_code,
        "error": error,
        "message": message,
    }
    return JSONResponse(status_code=status_code, content=body)
