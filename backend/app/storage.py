import asyncio
from io import BytesIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings


class ImageStore:
    """The bucket stays private. Only the API reads images for public products."""

    def __init__(self, settings: Settings):
        self.bucket = settings.s3_bucket
        self.max_bytes = settings.max_image_bytes
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4", s3={"addressing_style": "path"},
                connect_timeout=5, read_timeout=15, retries={"max_attempts": 2},
            ),
        )

    async def ensure_bucket(self) -> None:
        try:
            await self.check()
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            options = {"Bucket": self.bucket}
            if self.client.meta.region_name != "us-east-1":
                options["CreateBucketConfiguration"] = {"LocationConstraint": self.client.meta.region_name}
            try:
                await asyncio.to_thread(self.client.create_bucket, **options)
            except ClientError as create_exc:
                if create_exc.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

    async def check(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=key,
            Body=BytesIO(data), ContentType=content_type,
        )

    def _read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            if response["ContentLength"] > self.max_bytes:
                raise ValueError("Stored image exceeds the configured limit")
            data = body.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ValueError("Stored image exceeds the configured limit")
            return data
        finally:
            body.close()

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._read, key)

    def close(self) -> None:
        self.client.close()
