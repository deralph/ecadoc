"""Profile management service"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import asdict
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from modules.config.settings import settings
from modules.database.models import db_manager, UserProfilePhoto


class ProfileService:
    def __init__(self, db=None, s3_client=None):
        self.db = db or db_manager
        self.backend = settings.PROFILE_STORAGE_BACKEND.lower()
        self.bucket = settings.AWS_S3_BUCKET
        self.region = settings.AWS_DEFAULT_REGION
        self.folder = settings.PROFILE_S3_FOLDER.strip("/") if settings.PROFILE_S3_FOLDER else "profile-avatars"
        self.cdn_base = settings.PROFILE_CDN_BASE_URL.strip("/") if settings.PROFILE_CDN_BASE_URL else None
        self.s3 = None
        if self.backend == "s3" and self.bucket:
            self.s3 = s3_client or boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

    def _build_object_key(self, user_id: int, filename: str) -> str:
        ext = os.path.splitext(filename or "")[1] or ".png"
        return f"{self.folder}/{user_id}/{uuid.uuid4().hex}{ext}"

    def _build_public_url(self, object_key: str) -> str:
        if self.cdn_base:
            return f"{self.cdn_base}/{object_key}"
        if self.backend == "s3" and self.bucket and self.region:
            return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{object_key}"
        return object_key

    def _store_locally(self, object_key: str, data: bytes) -> Dict[str, Any]:
        base_dir = os.path.join(settings.DATA_DIR, self.folder)
        os.makedirs(base_dir, exist_ok=True)
        filename = object_key.split("/")[-1]
        path = os.path.join(base_dir, filename)
        with open(path, "wb") as handle:
            handle.write(data)
        etag = hashlib.md5(data).hexdigest()  # nosec - cache fingerprint
        return {
            "object_key": filename,
            "url": f"/download?path={path}",
            "etag": etag,
        }

    def _store_in_s3(self, object_key: str, data: bytes, content_type: str) -> Dict[str, Any]:
        if not self.s3:
            raise ValueError("S3 client is not configured")

        try:
            response = self.s3.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
                ACL="public-read",
                CacheControl="public, max-age=31536000",
            )
            etag = response.get("ETag", "").replace('"', '')
            return {
                "object_key": object_key,
                "url": self._build_public_url(object_key),
                "etag": etag,
            }
        except (BotoCoreError, ClientError) as exc:
            raise ValueError(f"Failed to upload avatar to S3: {exc}")

    def save_avatar(self, user_id: int, filename: str, content_type: str, data: bytes) -> Dict[str, Any]:
        if not data:
            raise ValueError("Avatar payload is empty")

        object_key = self._build_object_key(user_id, filename)

        if self.backend == "s3" and self.bucket:
            stored = self._store_in_s3(object_key, data, content_type)
        else:
            stored = self._store_locally(object_key, data)

        photo = self.db.upsert_user_profile_photo(
            user_id=user_id,
            object_key=stored["object_key"],
            url=stored["url"],
            storage_backend=self.backend,
            etag=stored.get("etag"),
        )

        return {
            "user_id": user_id,
            "url": photo.url,
            "object_key": photo.object_key,
            "etag": photo.etag,
            "storage_backend": photo.storage_backend,
        }

    def get_avatar(self, user_id: int) -> Optional[Dict[str, Any]]:
        photo = self.db.get_user_profile_photo(user_id)
        if not photo:
            return None
        if isinstance(photo, UserProfilePhoto):
            payload = asdict(photo)
        else:
            payload = photo
        if payload.get("last_updated") and hasattr(payload["last_updated"], "isoformat"):
            payload["last_updated"] = payload["last_updated"].isoformat()
        return payload


profile_service = ProfileService()
