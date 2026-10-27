import httpx
import pytest_asyncio

from app.api import create_app
from app.bot import create_app as create_bot_app


@pytest_asyncio.fixture
async def api_without_database(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def test_public_liveness_needs_no_database(api_without_database):
    assert (await api_without_database.get("/health/live")).json() == {"status": "ok"}


async def test_authentication_precedes_body_parsing(api_without_database):
    response = await api_without_database.post("/internal/products", content=b"not even json")
    assert response.status_code == 401


async def test_invalid_content_type(api_without_database, auth):
    response = await api_without_database.post("/internal/products", content=b"{}", headers=auth)
    assert response.status_code == 415


async def test_bad_json_and_invalid_fields(api_without_database, auth):
    response = await api_without_database.post("/internal/products", content=b"{",
                                               headers={**auth, "Content-Type": "application/json"})
    assert response.status_code == 400
    response = await api_without_database.post("/internal/products", json={"name": ""}, headers=auth)
    assert response.status_code == 422


async def test_invalid_image_does_not_connect_to_database(api_without_database, auth, payload):
    response = await api_without_database.post("/internal/products", json={**payload, "image_base64": "Zm9v"}, headers=auth)
    assert response.status_code == 422


async def test_invalid_webhook_secret_does_not_connect_to_database(settings):
    app = create_bot_app(settings)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/telegram/webhook", json={"update_id": 1})).status_code == 403
    finally:
        await app.state.database.close()
