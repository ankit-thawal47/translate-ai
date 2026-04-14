import logging
from pathlib import Path

import boto3
from botocore.client import Config

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        buckets = self.client.list_buckets().get("Buckets", [])
        if not any(bucket["Name"] == self.bucket for bucket in buckets):
            self.client.create_bucket(Bucket=self.bucket)

    def upload_file(self, source_path: Path, key: str) -> str:
        logger.info("storage.upload.start key=%s path=%s", key, source_path)
        self.client.upload_file(str(source_path), self.bucket, key)
        return f"s3://{self.bucket}/{key}"

