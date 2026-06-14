import time
import uuid


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4()}"


def generate_user_id() -> str:
    return _generate_id("user")


def generate_rvc_model_id() -> str:
    return _generate_id("rvc")


def generate_train_job_id() -> str:
    return _generate_id("train")


def generate_song_infer_job_id() -> str:
    return _generate_id("song_infer")


def generate_upload_session_id() -> str:
    return _generate_id("upload")


def generate_audio_upload_id() -> str:
    return _generate_id("audio_upload")
