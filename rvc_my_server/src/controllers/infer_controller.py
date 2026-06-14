import logging

from fastapi import UploadFile

from src.middlewares.auth_middleware import AuthContext
from src.services.infer_service import (
    InferRuntimeError,
    InvalidInferRequestError,
    ModelNotFoundError,
    convert_voice,
)
from src.services.mixing_service import (
    InvalidMixingRequestError,
    MixingRuntimeError,
    mix_ai_cover,
)
from src.services.system_service import get_torch_status
from src.utils.send_response import send_error_response, send_success_response

logger = logging.getLogger(__name__)


class InferController:
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


    async def torch_status(self):
        try:
            result = get_torch_status()
            return send_success_response(200, "Torch status retrieved", result)
        except Exception as exc:
            logger.exception("Error in torch_status")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))

    async def mix(
        self,
        main_vocal_file: UploadFile,
        backup_vocal_file: UploadFile | None,
        instrumental_file: UploadFile | None,
        reverb_room_size: float,
        reverb_wet: float,
        reverb_dry: float,
        reverb_damping: float,
        main_gain: float,
        backup_gain: float,
        inst_gain: float,
        output_format: str,
        keep_local: bool,
        auth: AuthContext,
    ):
        try:
            result = mix_ai_cover(
                main_vocal_file=main_vocal_file,
                backup_vocal_file=backup_vocal_file,
                instrumental_file=instrumental_file,
                user_id=auth.user_id,
                reverb_room_size=reverb_room_size,
                reverb_wet=reverb_wet,
                reverb_dry=reverb_dry,
                reverb_damping=reverb_damping,
                main_gain=main_gain,
                backup_gain=backup_gain,
                inst_gain=inst_gain,
                output_format=output_format,
                keep_local=keep_local,
            )
            return send_success_response(200, "Audio mixing successful", result)
        except InvalidMixingRequestError as exc:
            return send_error_response(400, "VALIDATION_FAILED", str(exc))
        except MixingRuntimeError as exc:
            return send_error_response(500, "MIXING_FAILED", str(exc))
        except Exception as exc:
            logger.exception("Error in audio mixing")
            return send_error_response(500, "INTERNAL_SERVER_ERROR", str(exc))


infer_controller = InferController()
