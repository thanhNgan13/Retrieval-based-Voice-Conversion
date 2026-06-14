"""Route registration with APP_ROLE-based selection.

The same code base runs in 3 modes, distinguished by the APP_ROLE env var:
- ``all`` (default): every router — single-container / single-process deploy.
- ``light``: everything EXCEPT direct GPU infer/separation routes — runs in the CPU api-light
  container in docker-compose; safe to host on Cloud Run CPU.
- ``infer``: direct GPU infer/separation routes — runs in the GPU infer container; safe to
  host on Cloud Run GPU.

Workers don't go through this module (they run Celery, not Uvicorn).
"""
import os

from fastapi import FastAPI

from src.utils.constant import API_BASE_PATH


APP_ROLE = os.getenv("APP_ROLE", "all").lower()


def register_routes(app: FastAPI) -> None:
    # Imports are deferred into each branch because the infer-side modules pull
    # heavy deps (soundfile, torch, ...) that the api-light image deliberately
    # does NOT install. Importing them at module top would crash api-light.
    if APP_ROLE in ("all", "light"):
        from src.routes.admin_routes import router as admin_router
        from src.routes.auth_routes import router as auth_router
        from src.routes.rvc_model_routes import router as rvc_model_router
        from src.routes.song_infer_routes import router as song_infer_router
        from src.routes.train_routes import router as train_router
        from src.routes.user_routes import router as user_router

        app.include_router(
            auth_router, prefix=f"{API_BASE_PATH}/auth-services", tags=["Auth"]
        )
        app.include_router(
            user_router, prefix=f"{API_BASE_PATH}/user-services", tags=["User"]
        )
        app.include_router(
            rvc_model_router,
            prefix=f"{API_BASE_PATH}/rvc-model-services",
            tags=["RVC Model"],
        )
        app.include_router(
            train_router, prefix=f"{API_BASE_PATH}/train-services", tags=["Train"]
        )
        app.include_router(
            song_infer_router,
            prefix=f"{API_BASE_PATH}/song-infer-services",
            tags=["Song Infer Job"],
        )
        app.include_router(
            admin_router, prefix=f"{API_BASE_PATH}/admin-services", tags=["Admin"]
        )

    if APP_ROLE in ("all", "infer"):
        from src.routes.infer_routes import router as infer_router
        from src.routes.separation_routes import router as separation_router

        app.include_router(
            infer_router, prefix=f"{API_BASE_PATH}/infer-services", tags=["Infer"]
        )
        app.include_router(
            separation_router,
            prefix=f"{API_BASE_PATH}/separation-services",
            tags=["Separation"],
        )
