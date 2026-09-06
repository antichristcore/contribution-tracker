from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from backend.app.config import settings

bot: Bot | None = Bot(
    token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML")
) if settings.BOT_TOKEN else None

dp = Dispatcher(storage=MemoryStorage())
