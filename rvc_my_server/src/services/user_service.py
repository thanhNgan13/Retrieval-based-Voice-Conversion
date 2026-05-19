from src.models.user_model import get_user_by_id
from src.utils.data_transform import convert_firestore_doc


class UserNotFoundError(Exception):
    pass


_PRIVATE_DROP_KEYS = ("password_hash",)


def get_my_profile(user_id: str) -> dict:
    doc = get_user_by_id(user_id)
    if not doc:
        raise UserNotFoundError("User not found")
    return convert_firestore_doc(doc, drop_keys=_PRIVATE_DROP_KEYS)
