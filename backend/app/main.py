import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram.types import MenuButtonWebApp, WebAppInfo
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.bot.bot_instance import bot, dp
from backend.app.bot.handlers import router as bot_router
from backend.app.config import settings
from backend.app.db import Base, engine
from backend.app.routers import auth, bootstrap, github_sync, members, presentation, scores, tasks, teams
from backend.app.services.scheduler import start_scheduler, scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

dp.include_router(bot_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    polling_task = None
    if bot:
        polling_task = asyncio.create_task(dp.start_polling(bot))
        if settings.MINI_APP_URL:
            # Persistent menu button (next to the message input) that opens
            # the Mini App directly — no /start round-trip needed first.
            try:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=settings.MINI_APP_URL))
                )
            except Exception:
                logger.exception("Failed to set the bot's default menu button")
    else:
        logger.warning("BOT_TOKEN not set — Telegram bot polling disabled")

    start_scheduler()

    yield

    scheduler.shutdown(wait=False)
    if polling_task:
        polling_task.cancel()
    if bot:
        await bot.session.close()


app = FastAPI(title="Contribution Tracker", lifespan=lifespan)

app.include_router(auth.me_router)
app.include_router(bootstrap.router)
app.include_router(teams.router)
app.include_router(members.router)
app.include_router(tasks.router)
app.include_router(github_sync.router)
app.include_router(scores.router)
app.include_router(presentation.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():

    @app.middleware("http")
    async def no_cache_index_html(request, call_next):
        # Telegram's in-app browser caches aggressively. Hashed files under
        # /assets/ are safe to cache forever (a rebuild gets a new filename),
        # but index.html must always be revalidated — otherwise it keeps
        # pointing at a deleted old bundle after every redeploy.
        response = await call_next(request)
        if request.url.path in ("/", "/index.html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        elif request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
