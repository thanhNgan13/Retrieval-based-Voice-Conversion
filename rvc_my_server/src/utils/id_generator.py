import time
import uuid


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4()}"


def generate_user_id() -> str:
    return _generate_id("user")


def generate_voice_id() -> str:
    return _generate_id("voice")


def generate_conversion_id() -> str:
    return _generate_id("conv")
