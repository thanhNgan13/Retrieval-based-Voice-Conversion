import logging
from typing import Optional

from src.middlewares.auth_middleware import AuthContext
from src.schemas.train_schema import (
    CreateTrainJobRequest,
    CreateTrainUploadUrlsRequest,
    DeleteTrainingUploadsRequest,
)
from src.services.train_service import (
    InvalidTrainRequestError,
    TrainJobNotFoundError,
    create_train_job,
    create_training_upload_urls,
    delete_all_uploaded_training_audios,
    delete_uploaded_training_audios,
    get_private_rvc_model_detail,
    get_train_job_detail,
    list_uploaded_training_audios,
    list_private_rvc_models,
    list_train_jobs,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class TrainController:
    async def create_upload_urls(
        self,
        body: CreateTrainUploadUrlsRequest,
        auth: AuthContext,
    ):
        try:
            result = create_training_upload_urls(body, auth.user_id)
            return send_success_response(201, "Signed upload URLs created", result)
        except InvalidTrainRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in create training upload urls")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def create_job(self, body: CreateTrainJobRequest, auth: AuthContext):
        try:
            result = create_train_job(body, auth.user_id)
            return send_success_response(202, "Training job queued", result)
        except InvalidTrainRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in create training job")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_jobs(self, limit: int, start_after: Optional[str], auth: AuthContext):
        try:
            result = list_train_jobs(auth.user_id, limit, start_after)
            return send_success_response(200, "Training jobs retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error in list training jobs")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def job_detail(self, train_job_id: str, auth: AuthContext):
        try:
            result = get_train_job_detail(train_job_id, auth.user_id)
            return send_success_response(200, "Training job retrieved successfully", result)
        except TrainJobNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in get training job")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_uploads(self, auth: AuthContext):
        try:
            result = list_uploaded_training_audios(auth.user_id)
            return send_success_response(
                200,
                "Uploaded training audio files retrieved successfully",
                result,
            )
        except Exception as exc:
            logger.exception("Error in list uploaded training audio files")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def delete_uploads(
        self,
        delete_all: bool,
        body: Optional[DeleteTrainingUploadsRequest],
        auth: AuthContext,
    ):
        try:
            if delete_all:
                result = delete_all_uploaded_training_audios(auth.user_id)
                message = "All uploaded training audio files deleted successfully"
            else:
                if body is None:
                    return send_error_response(
                        400,
                        "VALIDATION_FAILED",
                        "audioUploadIds or objectPaths body is required when deleteAll=false",
                    )
                result = delete_uploaded_training_audios(
                    user_id=auth.user_id,
                    object_paths=body.object_paths,
                    audio_upload_ids=body.audio_upload_ids,
                )
                message = "Uploaded training audio files deleted successfully"
            return send_success_response(
                200,
                message,
                result,
            )
        except InvalidTrainRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in delete uploaded training audio files")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def list_models(self, limit: int, start_after: Optional[str], auth: AuthContext):
        try:
            result = list_private_rvc_models(auth.user_id, limit, start_after)
            return send_success_response(200, "Private RVC models retrieved successfully", result)
        except Exception as exc:
            logger.exception("Error in list private RVC models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def model_detail(self, rvc_model_id: str, auth: AuthContext):
        try:
            result = get_private_rvc_model_detail(rvc_model_id, auth.user_id)
            return send_success_response(200, "Private RVC model retrieved successfully", result)
        except TrainJobNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except Exception as exc:
            logger.exception("Error in get private RVC model")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


train_controller = TrainController()
