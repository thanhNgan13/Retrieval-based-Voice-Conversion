import logging

from fastapi import UploadFile

from src.middlewares.auth_middleware import AuthContext
from src.services.infer_service import (
    InferRuntimeError,
    InvalidInferRequestError,
    ModelNotFoundError,
    convert_voice,
)
from src.services.separation_service import (
    InvalidSeparationRequestError,
    SeparationRuntimeError,
    list_uvr5_models,
    separate_song,
)
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class InferController:
    async def separation_models(self):
        try:
            result = list_uvr5_models()
            return send_success_response(200, "UVR5 models retrieved", result)
        except Exception as exc:
            logger.exception("Error in list UVR5 models")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def separate(
        self,
        audio_file: UploadFile,
        model_name: str,
        agg: int,
        output_format: str,
        keep_local: bool,
        auth: AuthContext,
    ):
        try:
            result = separate_song(
                audio_file=audio_file,
                user_id=auth.user_id,
                model_name=model_name,
                agg=agg,
                output_format=output_format,
                keep_local=keep_local,
            )
            return send_success_response(200, "Audio separation successful", result)
        except InvalidSeparationRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except SeparationRuntimeError as exc:
            return send_error_response(500, "SEPARATION_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in audio separation")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def convert(
        self,
        audio_file: UploadFile,
        rvc_model_id: str,
        speaker_id: int,
        f0_up_key: int,
        f0_method: str,
        index_rate: float,
        filter_radius: int,
        resample_sr: int,
        rms_mix_rate: float,
        protect: float,
        auth: AuthContext,
    ):
        try:
            result = convert_voice(
                audio_file=audio_file,
                rvc_model_id=rvc_model_id,
                speaker_id=speaker_id,
                f0_up_key=f0_up_key,
                f0_method=f0_method,
                index_rate=index_rate,
                filter_radius=filter_radius,
                resample_sr=resample_sr,
                rms_mix_rate=rms_mix_rate,
                protect=protect,
                user_id=auth.user_id,
            )
            return send_success_response(200, "Voice conversion successful", result)
        except InvalidInferRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except ModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except InferRuntimeError as exc:
            return send_error_response(500, "INFER_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in voice conversion")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def convert_private(
        self,
        audio_file: UploadFile,
        rvc_model_id: str,
        speaker_id: int,
        f0_up_key: int,
        f0_method: str,
        index_rate: float,
        filter_radius: int,
        resample_sr: int,
        rms_mix_rate: float,
        protect: float,
        auth: AuthContext,
    ):
        try:
            result = convert_voice(
                audio_file=audio_file,
                rvc_model_id=rvc_model_id,
                speaker_id=speaker_id,
                f0_up_key=f0_up_key,
                f0_method=f0_method,
                index_rate=index_rate,
                filter_radius=filter_radius,
                resample_sr=resample_sr,
                rms_mix_rate=rms_mix_rate,
                protect=protect,
                user_id=auth.user_id,
                private_only=True,
            )
            return send_success_response(200, "Private voice conversion successful", result)
        except InvalidInferRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except ModelNotFoundError as exc:
            return send_error_response(404, "NOT_FOUND", str(exc))
        except InferRuntimeError as exc:
            return send_error_response(500, "INFER_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in private voice conversion")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


infer_controller = InferController()
