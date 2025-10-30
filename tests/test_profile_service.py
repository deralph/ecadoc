import os
import uuid

from modules.config import settings
from modules.database.models import DatabaseManager
from modules.profile.service import ProfileService


def test_profile_avatar_local_storage(tmp_path):
    settings.PROFILE_STORAGE_BACKEND = "local"
    settings.PROFILE_S3_FOLDER = "avatars-test"
    settings.DATA_DIR = str(tmp_path)

    db = DatabaseManager(db_name=str(tmp_path / "profile.db"))
    service = ProfileService(db=db)
    email = f"pic+{uuid.uuid4().hex}@example.com"
    user_id = db.create_user("Pic", "User", email, "password123")

    payload = service.save_avatar(user_id, "avatar.png", "image/png", b"binary-data")
    assert payload["url"].startswith("/download?path=")

    stored = service.get_avatar(user_id)
    assert stored["object_key"].endswith(".png")
    download_path = stored["url"].split("=", 1)[1]
    assert os.path.exists(download_path)
