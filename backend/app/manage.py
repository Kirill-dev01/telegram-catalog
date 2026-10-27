"""One-shot commands, deliberately separate from replica startup."""
import argparse
import asyncio
import base64
from io import BytesIO

import httpx
from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from PIL import Image, ImageDraw
from sqlalchemy import func, select, update

from app.config import Settings
from app.database import Database
from app.models import TelegramUpdate
from app.storage import ImageStore


async def main(command: str):
    settings = Settings()
    if command == "init-storage":
        store = ImageStore(settings)
        try:
            await store.ensure_bucket()
            print("Private image bucket ready.")
        finally:
            store.close()
    elif command in {"set-webhook", "webhook-info"}:
        if not settings.bot_token:
            raise SystemExit("Set BOT_TOKEN in .env first.")
        async with Bot(settings.bot_token) as bot:
            if command == "set-webhook":
                if not settings.public_base_url.startswith("https://"):
                    raise SystemExit("PUBLIC_BASE_URL must be public HTTPS for Telegram.")
                await bot.set_webhook(
                    settings.public_base_url + "/telegram/webhook",
                    secret_token=settings.webhook_secret, allowed_updates=["message"],
                    drop_pending_updates=False,
                )
                await bot.set_my_commands([
                    BotCommand(command="start", description="Открыть каталог"),
                    BotCommand(command="create", description="Создать товар (администратор)"),
                    BotCommand(command="id", description="Мой Telegram ID"),
                ])
                await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                    text="Каталог", web_app=WebAppInfo(url=settings.public_base_url)))
                print("Webhook and Mini App menu configured. Pending updates preserved.")
            else:
                info = await bot.get_webhook_info()
                print(f"URL: {info.url}\nPending: {info.pending_update_count}\nLast error: {info.last_error_message}")
    elif command == "seed":
        async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=30,
                                      headers={"Authorization": "Bearer " + settings.internal_api_token}) as client:
            for index, (name, color) in enumerate([
                ("Керамическая кружка", "#d3bc9e"), ("Настольная лампа", "#859b8f"),
                ("Записная книжка", "#a4afc0"), ("Хлопковая сумка", "#c49b87"),
            ], 1):
                image = Image.new("RGB", (600, 450), color)
                draw = ImageDraw.Draw(image)
                draw.rounded_rectangle((170, 100, 430, 350), radius=30, fill="#f6f4ee")
                draw.text((270, 210), f"DEMO {index}", fill="#243240")
                with BytesIO() as buffer:
                    image.save(buffer, format="JPEG")
                    response = await client.post("/internal/products", json={
                        "name": name, "source_key": f"demo:{index}",
                        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
                    })
                response.raise_for_status()
            print("4 demo products ready (re-running does not create duplicates).")
    else:
        database = Database(settings.database_url)
        try:
            async with database.sessions.begin() as session:
                if command == "retry-failed":
                    result = await session.execute(update(TelegramUpdate).where(
                        TelegramUpdate.failed_at.is_not(None), TelegramUpdate.processed_at.is_(None),
                    ).values(failed_at=None, attempts=0, available_at=func.now(), last_error=None))
                    print(f"Requeued: {result.rowcount}")
                elif command == "queue-status":
                    for name, condition in [
                        ("processed", TelegramUpdate.processed_at.is_not(None)),
                        ("failed", TelegramUpdate.failed_at.is_not(None)),
                        ("pending", TelegramUpdate.processed_at.is_(None) & TelegramUpdate.failed_at.is_(None)),
                    ]:
                        count = await session.scalar(select(func.count()).select_from(TelegramUpdate).where(condition))
                        print(f"{name}: {count}")
        finally:
            await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init-storage", "set-webhook", "webhook-info", "seed", "queue-status", "retry-failed"])
    arguments = parser.parse_args()
    try:
        asyncio.run(main(arguments.command))
    except Exception as exc:
        # Avoid leaking URLs containing tokens in an unhandled traceback.
        raise SystemExit(f"Command failed: {type(exc).__name__}. Check configuration and service health.") from None
