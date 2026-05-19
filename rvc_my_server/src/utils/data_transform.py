import re
from datetime import datetime
from typing import Any

_CAMEL_TO_SNAKE_RE = re.compile(r"(?<!^)(?=[A-Z])")


def snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def camel_to_snake(s: str) -> str:
    return _CAMEL_TO_SNAKE_RE.sub("_", s).lower()


def _convert_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return value
    return value


def deep_snake_to_camel(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {snake_to_camel(k): deep_snake_to_camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_snake_to_camel(item) for item in obj]
    return _convert_value(obj)


def deep_camel_to_snake(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {camel_to_snake(k): deep_camel_to_snake(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_camel_to_snake(item) for item in obj]
    return obj


def convert_firestore_doc(doc: dict, drop_keys: tuple = ()) -> dict:
    cleaned = {k: v for k, v in doc.items() if k not in drop_keys}
    return deep_snake_to_camel(cleaned)
