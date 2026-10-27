import asyncio

import httpx
import pytest
from sqlalchemy import func, select

from app.api import create_app
from app.models import Product

pytestmark = pytest.mark.integration


async def test_create_list_and_image(system, auth, payload, image_bytes):
    app, client = system
    created = await client.post("/internal/products", json=payload, headers=auth)
    assert created.status_code == 200, created.text
    result = (await client.get("/api/products")).json()
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == payload["name"]
    assert "source_key" not in result["items"][0]
    response = await client.get(result["items"][0]["image_url"])
    assert response.content == image_bytes
    assert response.headers["content-type"] == "image/jpeg"
    assert (await client.get("/health/ready")).status_code == 200


async def test_rejects_unauthorized_write(system, payload):
    _, client = system
    assert (await client.post("/internal/products", json=payload)).status_code == 401
    assert (await client.get("/api/products")).json()["items"] == []


async def test_rejects_conflicting_retry(system, auth, payload):
    _, client = system
    first = await client.post("/internal/products", json=payload, headers=auth)
    second = await client.post("/internal/products", json=payload, headers=auth)
    assert first.json()["id"] == second.json()["id"]
    conflicting = await client.post("/internal/products", json={**payload, "name": "Другой"}, headers=auth)
    assert conflicting.status_code == 409


async def test_two_api_instances_deduplicate_concurrent_create(system, settings, auth, payload):
    app, first = system
    other_app = create_app(settings)
    async with other_app.router.lifespan_context(other_app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other_app), base_url="http://second") as second:
            results = await asyncio.gather(*[
                (first if index % 2 else second).post("/internal/products", json=payload, headers=auth)
                for index in range(12)
            ])
            assert all(result.status_code == 200 for result in results)
            assert len({result.json()["id"] for result in results}) == 1
    async with app.state.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Product)) == 1


async def test_search_and_cursor_pagination(system, auth, payload):
    _, client = system
    for index, name in enumerate(["Лампа", "Кружка", "100% хлопок", "1000 хлопок"]):
        await client.post("/internal/products", json={**payload, "source_key": f"test:{index}", "name": name}, headers=auth)
    first = (await client.get("/api/products?limit=2")).json()
    second = (await client.get("/api/products", params={"limit": 2, "before": first["next_cursor"]})).json()
    assert len(first["items"]) == len(second["items"]) == 2
    assert not {p["id"] for p in first["items"]} & {p["id"] for p in second["items"]}
    assert second["next_cursor"] is None
    found = (await client.get("/api/products", params={"q": "100%"})).json()
    assert [p["name"] for p in found["items"]] == ["100% хлопок"]


async def test_invalid_image_does_not_create_product(system, auth, payload):
    _, client = system
    response = await client.post("/internal/products", json={**payload, "image_base64": "Zm9v"}, headers=auth)
    assert response.status_code == 422
    assert (await client.get("/api/products")).json()["items"] == []


async def test_missing_image_and_bad_pagination(system):
    _, client = system
    assert (await client.get("/api/products/999/image")).status_code == 404
    assert (await client.get("/api/products?limit=999")).status_code == 422
    assert (await client.get("/api/products?before=-1")).status_code == 422


async def test_large_body_is_rejected(system, auth, settings):
    _, client = system
    response = await client.post("/internal/products", content=b"x" * (settings.max_image_bytes * 2),
                                 headers={**auth, "Content-Type": "application/json"})
    assert response.status_code == 413


async def test_storage_failure_rolls_back_product(system, auth, payload, monkeypatch):
    app, client = system
    from botocore.exceptions import EndpointConnectionError

    async def broken_put(*args):
        raise EndpointConnectionError(endpoint_url="http://storage.invalid")

    monkeypatch.setattr(app.state.store, "put", broken_put)
    response = await client.post("/internal/products", json=payload, headers=auth)
    assert response.status_code == 503
    assert (await client.get("/api/products")).json()["items"] == []
