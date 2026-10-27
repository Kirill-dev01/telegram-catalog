import base64
from io import BytesIO

import httpx
from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import Settings


class BoundedBuffer(BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.limit:
            raise ValueError("Image exceeds limit")
        return super().write(data)


def create_router(settings: Settings, client: httpx.AsyncClient) -> Router:
    router = Router()
    # Admin creation and Web App buttons are intended for private bot chats.
    router.message.filter(F.chat.type == ChatType.PRIVATE)

    def is_admin(message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in settings.administrators)

    def catalog_keyboard() -> InlineKeyboardMarkup | None:
        if not settings.public_base_url.startswith("https://"):
            return None
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть каталог", web_app=WebAppInfo(url=settings.public_base_url)),
        ]])

    @router.message(Command("id"))
    async def show_id(message: Message):
        await message.answer(f"Ваш Telegram ID: {message.from_user.id}")

    @router.message(Command("create"))
    @router.message(F.text.casefold() == "создать товар")
    async def create_instruction(message: Message):
        if not is_admin(message):
            await message.answer("Добавлять товары может только администратор.")
            return
        await message.answer("Отправьте одно фото с названием товара в подписи (до 200 символов). "
                             "Фото и название должны быть в одном сообщении. Максимум 5 МБ.")

    @router.message(F.photo)
    async def receive_product(message: Message, bot: Bot):
        if not is_admin(message):
            await message.answer("Добавлять товары может только администратор.")
            return
        if message.media_group_id:
            await message.answer("Отправьте одно фото, а не альбом.")
            return
        name = " ".join((message.caption or "").split())
        if not name or len(name) > 200:
            await message.answer("Добавьте к фото название длиной от 1 до 200 символов.")
            return
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > settings.max_image_bytes:
            await message.answer("Фото слишком большое. Максимум 5 МБ.")
            return
        try:
            with BoundedBuffer(settings.max_image_bytes) as buffer:
                await bot.download(photo, destination=buffer, timeout=25)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        except ValueError:
            await message.answer("Фото слишком большое. Максимум 5 МБ.")
            return

        response = await client.post("/internal/products", json={
            "name": name, "image_base64": encoded,
            "source_key": f"telegram:{bot.id}:{message.chat.id}:{message.message_id}",
        })
        if response.status_code == 422:
            await message.answer("Не удалось принять изображение. Отправьте другое фото с названием.")
            return
        response.raise_for_status()  # Queue retries transient failures; no silent loss.
        product = response.json()
        await message.answer(f"Товар «{product['name']}» добавлен. № {product['id']}",
                             reply_markup=catalog_keyboard())

    @router.message()
    async def welcome(message: Message):
        text = "У меня есть товары"
        if is_admin(message):
            text += "\n\nСоздать товар: /create\nОтправьте фото с названием в подписи."
        if catalog_keyboard() is None:
            text += "\n\nКаталог пока доступен только локально. Кнопка появится после настройки HTTPS."
        await message.answer(text, reply_markup=catalog_keyboard())

    return router
