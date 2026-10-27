import logging
import secrets
from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.catalog import ConflictingRetry, InvalidImage, add_product, list_products, to_product_out
from app.config import Settings
from app.database import Database
from app.http import bounded_json
from app.models import Product
from app.schemas import ProductCreate, ProductOut, ProductPage
from app.storage import ImageStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    store = ImageStore(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        store.close()
        await database.close()

    app = FastAPI(title="Catalog API", lifespan=lifespan)
    app.state.database = database
    app.state.store = store

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(BotoCoreError)
    @app.exception_handler(ClientError)
    async def dependency_error(request: Request, exc: Exception):
        from fastapi.responses import JSONResponse
        logger.error("Dependency failure: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Сервис временно недоступен"})

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        async with database.sessions() as session:
            await session.execute(text("SELECT 1 FROM products LIMIT 1"))
        await store.check()
        return {"status": "ready"}

    @app.get("/api/products", response_model=ProductPage)
    async def products(response: Response, q: str = Query(default="", max_length=120),
                       before: int | None = Query(default=None, gt=0),
                       limit: int = Query(default=24, ge=1, le=60)):
        response.headers["Cache-Control"] = "no-store"
        async with database.sessions() as session:
            return await list_products(session, q.strip(), before, limit)

    @app.get("/api/products/{product_id}/image")
    async def product_image(product_id: int):
        async with database.sessions() as session:
            product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(404, "Товар не найден")
        data = await store.read(product.image_key)
        return Response(data, media_type=product.image_type, headers={
            "Cache-Control": "public, max-age=86400, immutable", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        })

    @app.post("/internal/products", response_model=ProductOut)
    async def create_product(request: Request):
        token = request.headers.get("authorization", "")
        if not secrets.compare_digest(token.encode(), ("Bearer " + settings.internal_api_token).encode()):
            raise HTTPException(401, "Unauthorized")
        raw = await bounded_json(request, ((settings.max_image_bytes + 2) // 3) * 4 + 4096)
        try:
            payload = ProductCreate.model_validate(raw)
        except ValidationError as exc:
            # Do not echo uploaded base64 or credentials in validation errors.
            raise HTTPException(422, "Проверьте название, ключ и изображение") from exc
        try:
            async with database.sessions.begin() as session:
                product = await add_product(session, store, payload)
                result = to_product_out(product)
            return result
        except InvalidImage as exc:
            raise HTTPException(422, str(exc)) from exc
        except ConflictingRetry as exc:
            raise HTTPException(409, str(exc)) from exc

    return app
