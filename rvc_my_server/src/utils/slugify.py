import re
import unicodedata

# Vietnamese đ/Đ is not handled by NFD decomposition — map manually first.
_VN_MAP = str.maketrans({"đ": "d", "Đ": "D"})


def slugify(text: str, max_length: int = 60) -> str:
    if not text:
        return "untitled"
    s = text.translate(_VN_MAP)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return "untitled"
    return s[:max_length].rstrip("-") or "untitled"
