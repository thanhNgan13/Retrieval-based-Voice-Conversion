import re

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 80


def is_valid_email(email: str) -> bool:
    return bool(email) and bool(_EMAIL_RE.match(email))


def is_valid_password(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password or "") <= MAX_PASSWORD_LENGTH


def is_valid_name(name: str) -> bool:
    if not name:
        return False
    n = name.strip()
    return MIN_NAME_LENGTH <= len(n) <= MAX_NAME_LENGTH
