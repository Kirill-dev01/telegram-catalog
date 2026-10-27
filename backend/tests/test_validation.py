import base64

import pytest
from pydantic import ValidationError

from app.bot_handlers import BoundedBuffer
from app.catalog import InvalidImage, validate_image
from app.schemas import ProductCreate


def test_real_image_is_accepted(image_bytes):
    data, kind = validate_image(base64.b64encode(image_bytes).decode(), 1024 * 1024)
    assert data == image_bytes
    assert kind == "image/jpeg"


@pytest.mark.parametrize("encoded", ["bad!base64", base64.b64encode(b"<script>alert(1)</script>").decode(), ""])
def test_invalid_images_are_rejected(encoded):
    with pytest.raises(InvalidImage):
        validate_image(encoded, 1024)


def test_large_image_is_rejected(image_bytes):
    with pytest.raises(InvalidImage):
        validate_image(base64.b64encode(image_bytes).decode(), 10)


def test_whitespace_name_is_rejected(payload):
    with pytest.raises(ValidationError):
        ProductCreate(**{**payload, "name": " \n "})


def test_name_normalization(payload):
    assert ProductCreate(**{**payload, "name": "  Мой\n товар  "}).name == "Мой товар"


def test_download_is_bounded():
    with BoundedBuffer(5) as stream:
        stream.write(b"123")
        with pytest.raises(ValueError):
            stream.write(b"456")


def test_admin_allowlist_is_parsed(settings):
    assert settings.administrators == frozenset({42})
