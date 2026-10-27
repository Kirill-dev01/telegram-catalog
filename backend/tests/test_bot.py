from datetime import datetime, timezone

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetFile, SendMessage
from aiogram.types import File, Message, Update

from app.bot import create_app
from app.bot_handlers import create_router


class FakeTelegramSession(BaseSession):
    """No requests to real Telegram: records replies and returns a test photo."""
    def __init__(self, image_bytes=b""):
        super().__init__()
        self.calls = []
        self.image_bytes = image_bytes

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=999, date=datetime.now(timezone.utc),
                           chat={"id": method.chat_id, "type": "private"}, text=method.text)
        if isinstance(method, GetFile):
            return File(file_id="photo", file_unique_id="photo-unique", file_path="photos/test.jpg")
        raise AssertionError(f"Unexpected Telegram call: {type(method).__name__}")

    async def stream_content(self, url, **kwargs):
        yield self.image_bytes


def make_update(user=42, text=None, photo=False, caption=None, update_id=1):
    message = {"message_id": 10, "date": 1735689600, "chat": {"id": user, "type": "private"},
               "from": {"id": user, "is_bot": False, "first_name": "Tester"}}
    if text is not None:
        message["text"] = text
    if photo:
        message["photo"] = [{"file_id": "photo", "file_unique_id": "photo-unique", "width": 64, "height": 48}]
    if caption is not None:
        message["caption"] = caption
    return Update.model_validate({"update_id": update_id, "message": message})


async def test_start_offers_mini_app(settings):
    telegram = FakeTelegramSession()
    bot = Bot(settings.bot_token, session=telegram)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        dispatcher = Dispatcher(disable_fsm=True)
        dispatcher.include_router(create_router(settings, client))
        await dispatcher.feed_update(bot, make_update(text="/start"))
    reply = telegram.calls[-1]
    assert "У меня есть товары" in reply.text
    assert reply.reply_markup.inline_keyboard[0][0].web_app.url == settings.public_base_url


async def test_non_admin_cannot_add_product(settings):
    telegram = FakeTelegramSession()
    bot = Bot(settings.bot_token, session=telegram)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        dispatcher = Dispatcher(disable_fsm=True)
        dispatcher.include_router(create_router(settings, client))
        await dispatcher.feed_update(bot, make_update(user=99, photo=True, caption="Sneaky"))
    assert "только администратор" in telegram.calls[-1].text
    assert not any(isinstance(call, GetFile) for call in telegram.calls)


async def test_missing_caption_is_explained(settings):
    telegram = FakeTelegramSession()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        dispatcher = Dispatcher(disable_fsm=True)
        dispatcher.include_router(create_router(settings, client))
        await dispatcher.feed_update(Bot(settings.bot_token, session=telegram), make_update(photo=True))
    assert "название" in telegram.calls[-1].text


@pytest.mark.integration
async def test_admin_photo_reaches_api_and_replay_does_not_duplicate(system, settings, image_bytes, auth):
    app, client = system
    client.headers.update(auth)
    telegram = FakeTelegramSession(image_bytes)
    bot = Bot(settings.bot_token, session=telegram)
    dispatcher = Dispatcher(disable_fsm=True)
    dispatcher.include_router(create_router(settings, client))
    update = make_update(photo=True, caption="Новая кружка")
    await dispatcher.feed_update(bot, update)
    await dispatcher.feed_update(bot, update)
    products = (await client.get("/api/products")).json()["items"]
    assert len(products) == 1
    assert products[0]["name"] == "Новая кружка"
    assert "добавлен" in telegram.calls[-1].text


@pytest.mark.integration
async def test_webhook_requires_secret_and_persists_update(system, settings):
    app = create_app(settings)
    # Do not start the real worker; this test exercises ingress and durable storage.
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            payload = make_update(text="/start").model_dump(mode="json", exclude_none=True)
            assert (await client.post("/telegram/webhook", json=payload)).status_code == 403
            headers = {"X-Telegram-Bot-Api-Secret-Token": settings.webhook_secret}
            assert (await client.post("/telegram/webhook", json=payload, headers=headers)).status_code == 200
            assert (await client.post("/telegram/webhook", json=payload, headers=headers)).status_code == 200
            job = await app.state.queue.claim()
            assert job.update_id == 1
            assert await app.state.queue.claim() is None
    finally:
        await app.state.database.close()
