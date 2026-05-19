import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, storage

from src.config.settings import settings

_initialized = False


def init_firebase() -> None:
    global _initialized
    if _initialized:
        return

    options = {}
    if settings.FIREBASE_STORAGE_BUCKET:
        options["storageBucket"] = settings.FIREBASE_STORAGE_BUCKET

    # When FIRESTORE_EMULATOR_HOST is set, the SDK auto-routes to the emulator
    # and credentials are not required. We still need a project_id.
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        if settings.FIREBASE_PROJECT_ID:
            options["projectId"] = settings.FIREBASE_PROJECT_ID
        firebase_admin.initialize_app(options=options or None)
    else:
        cred_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if cred_path and Path(cred_path).is_file():
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, options or None)
        else:
            # ADC fallback (e.g. on Cloud Run with attached service account)
            firebase_admin.initialize_app(options=options or None)

    _initialized = True


def get_db():
    init_firebase()
    return firestore.client()


def get_bucket():
    init_firebase()
    return storage.bucket()
