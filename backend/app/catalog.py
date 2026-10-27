import asyncio
import base64
import binascii
import hashlib
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product
from app.schemas import ProductCreate, ProductOut, ProductPage
from app.storage import ImageStore


class InvalidImage(ValueError):
    pass


class ConflictingRetry(ValueError):
    pass


def validate_image(encoded: str, max_bytes: int) -> tuple[bytes, str]:
    if len(encoded) > ((max_bytes + 2) // 3) * 4:
        raise InvalidImage("Изображение слишком большое")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidImage("Некорректный base64") from exc
    if not data or len(data) > max_bytes:
        raise InvalidImage("Изображение пустое или слишком большое")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image.format)
                if not image_type or image.width * image.height > 25_000_000:
                    raise InvalidImage("Нужен JPEG, PNG или WebP размером до 25 мегапикселей")
                image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("Файл не является корректным изображением") from exc
    return data, image_type


def to_product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id, name=product.name,
        image_url=f"/api/products/{product.id}/image", created_at=product.created_at,
    )


async def add_product(session: AsyncSession, store: ImageStore, payload: ProductCreate) -> Product:
    data, image_type = await asyncio.to_thread(validate_image, payload.image_base64, store.max_bytes)
    image_hash = hashlib.sha256(data).hexdigest()
    payload_hash = hashlib.sha256((payload.name + "\0" + image_hash).encode()).hexdigest()
    lock_id = int.from_bytes(hashlib.sha256(payload.source_key.encode()).digest()[:8], "big", signed=True)

    # Serialize equal source keys across every API replica, not just this process.
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    existing = await session.scalar(select(Product).where(Product.source_key == payload.source_key))
    if existing:
        if existing.payload_hash != payload_hash:
            raise ConflictingRetry("Этот ключ уже использован для другого товара")
        return existing

    # A crash after S3 upload can leave an orphan object. A retry reuses its key.
    image_key = f"products/{image_hash}"
    await store.put(image_key, data, image_type)
    product = Product(name=payload.name, image_key=image_key, image_type=image_type,
                      source_key=payload.source_key, payload_hash=payload_hash)
    session.add(product)
    await session.flush()
    return product


async def list_products(session: AsyncSession, query: str, before: int | None, limit: int) -> ProductPage:
    statement = select(Product).order_by(Product.id.desc()).limit(limit + 1)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Product.name.ilike(f"%{escaped}%", escape="\\"))
    if before is not None:
        statement = statement.where(Product.id < before)
    products = list((await session.scalars(statement)).all())
    return ProductPage(
        items=[to_product_out(product) for product in products[:limit]],
        next_cursor=products[limit - 1].id if len(products) > limit else None,
    )
