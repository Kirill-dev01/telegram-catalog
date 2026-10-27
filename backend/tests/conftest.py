import base64
import os
import subprocess
import sys
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from moto import mock_aws
from PIL import Image
from sqlalchemy import text

from app.api import create_app
from app.config import Settings


@pytest.fixture
def image_bytes():
    with BytesIO() as stream:
        Image.new("RGB", (64, 48), "#557799").save(stream, "JPEG")
        return stream.getvalue()


@pytest.fixture
def payload(image_bytes):
    return {"name": "Тестовый товар", "source_key": "test:1", "image_base64": base64.b64encode(image_bytes).decode()}


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url=os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://test:test@localhost/catalog_test"),
        internal_api_token="test-internal-token-" + "x" * 32,
        s3_endpoint=os.environ.get("TEST_S3_ENDPOINT", "https://s3.amazonaws.com"),
        s3_access_key=os.environ.get("TEST_S3_ACCESS_KEY", "testing"),
        s3_secret_key=os.environ.get("TEST_S3_SECRET_KEY", "testing-secret-key-for-tests"),
        s3_bucket="catalog-test-" + uuid4().hex,
        webhook_secret="test-webhook-secret-" + "x" * 32,
        bot_token="123456789:" + "A" * 35,
        admin_ids="42", public_base_url="https://catalog.example.test",
    )


@pytest.fixture(scope="session")
def migrated_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    from sqlalchemy.engine import make_url
    if not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("Refusing to reset a database whose name does not end in _test")
    environment = {**os.environ, "DATABASE_URL": url, "INTERNAL_API_TOKEN": "x" * 32,
                   "S3_ACCESS_KEY": "testing", "S3_SECRET_KEY": "x" * 32, "WEBHOOK_SECRET": "x" * 32}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=Path(__file__).resolve().parents[1], env=environment, check=True, timeout=60)
    return url


@pytest_asyncio.fixture
async def system(settings, migrated_database):
    # Default: real PostgreSQL + S3 emulator. Optional env switches to real MinIO.
    context = nullcontext() if os.environ.get("TEST_S3_ENDPOINT") else mock_aws()
    with context:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            await app.state.store.ensure_bucket()
            async with app.state.database.sessions.begin() as session:
                await session.execute(text("TRUNCATE products, telegram_updates RESTART IDENTITY"))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield app, client
            if os.environ.get("TEST_S3_ENDPOINT"):
                s3 = app.state.store.client
                objects = s3.list_objects_v2(Bucket=settings.s3_bucket).get("Contents", [])
                for item in objects:
                    s3.delete_object(Bucket=settings.s3_bucket, Key=item["Key"])
                s3.delete_bucket(Bucket=settings.s3_bucket)


@pytest.fixture
def auth(settings):
    return {"Authorization": "Bearer " + settings.internal_api_token}
