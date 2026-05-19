from fastapi import FastAPI

from src.routes.admin_routes import router as admin_router
from src.routes.auth_routes import router as auth_router
from src.routes.rvc_model_routes import router as rvc_model_router
from src.routes.user_routes import router as user_router
from src.utils.constant import API_BASE_PATH


def register_routes(app: FastAPI) -> None:
    app.include_router(auth_router, prefix=f"{API_BASE_PATH}/auth-services", tags=["Auth"])
    app.include_router(user_router, prefix=f"{API_BASE_PATH}/user-services", tags=["User"])
    app.include_router(
        rvc_model_router,
        prefix=f"{API_BASE_PATH}/rvc-model-services",
        tags=["RVC Model"],
    )
    app.include_router(
        admin_router,
        prefix=f"{API_BASE_PATH}/admin-services",
        tags=["Admin"],
    )
