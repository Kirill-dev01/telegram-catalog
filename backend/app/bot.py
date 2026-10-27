import asyncio
import logging
import secrets
from contextlib import asynccontextmanager, suppress

import httpx
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.bot_handlers import create_router
from app.config import Settings
from app.database import Database
from app.http import bounded_json
from app.queue import UpdateQueue

logger = logging.getLogger(__name__)


async def run_worker(queue: UpdateQueue, dispatcher: Dispatcher, bot: Bot, settings: Settings):
    while True:
        try:
            job = await queue.claim()
            if job is None:
                await asyncio.sleep(settings.worker_poll_seconds)
                continue
            try:
                async with asyncio.timeout(settings.worker_timeout_seconds):
                    update = Update.model_validate(job.payload, context={"bot": bot})
                    await dispatcher.feed_update(bot, update)
                await queue.complete(job)
            except Exception as exc:
                # Never log full exceptions: Telegram URLs can contain the bot token.
                logger.warning("Update %s failed: %s", job.update_id, type(exc).__name__)
                retry_after = exc.retry_after if isinstance(exc, TelegramRetryAfter) else None
                await queue.fail(job, type(exc).__name__, retry_after)
        except asyncio.CancelledError:
            # The durable lease expires, so another instance can recover this job.
            raise
        except Exception as exc:
            logger.error("Queue unavailable: %s", type(exc).__name__)
            await asyncio.sleep(2)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    queue = UpdateQueue(database, settings.job_lease_seconds, settings.job_max_attempts)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        bot = None
        client = httpx.AsyncClient(
            base_url=settings.api_base_url, timeout=30,
            headers={"Authorization": "Bearer " + settings.internal_api_token},
        )
        if settings.bot_token:
            bot = Bot(settings.bot_token)
            dispatcher = Dispatcher(disable_fsm=True)
            dispatcher.include_router(create_router(settings, client))
            task = asyncio.create_task(run_worker(queue, dispatcher, bot, settings))
        app.state.worker = task
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if bot:
                await bot.session.close()
            await client.aclose()
            await database.close()

    app = FastAPI(title="Telegram webhook", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.queue = queue
    app.state.database = database

    @app.get("/health/live")
    async def live():
        return {"status": "ok", "configured": bool(settings.bot_token)}

    @app.get("/health/ready")
    async def ready():
        if not settings.bot_token:
            raise HTTPException(503, "Bot token is not configured")
        if app.state.worker.done():
            raise HTTPException(503, "Worker stopped")
        async with database.sessions() as session:
            await session.execute(text("SELECT 1 FROM telegram_updates LIMIT 1"))
        return {"status": "ready"}

    @app.post("/telegram/webhook")
    async def webhook(request: Request):
        if not secrets.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", "").encode(),
                                      settings.webhook_secret.encode()):
            raise HTTPException(403, "Invalid webhook secret")
        if not settings.bot_token:
            raise HTTPException(503, "Bot token is not configured")
        payload = await bounded_json(request, 256 * 1024)
        try:
            update = Update.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid Telegram update") from exc
        # Acknowledge only after PostgreSQL commit, never after an in-memory enqueue.
        try:
            await queue.enqueue(update.update_id, payload)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Update storage temporarily unavailable") from exc
        return {"ok": True}

    return app
