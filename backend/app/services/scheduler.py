import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import Team
from backend.app.services.github_sync_service import sync_team
from backend.app.services.recalc import recalculate_team_scores

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()


async def sync_all_teams_job() -> None:
    db = SessionLocal()
    try:
        for team in db.query(Team).all():
            try:
                await sync_team(db, team)
            except Exception:
                logger.exception("GitHub sync failed for team %s", team.id)
    finally:
        db.close()


async def recalc_all_scores_job() -> None:
    db = SessionLocal()
    try:
        for team in db.query(Team).all():
            try:
                await recalculate_team_scores(db, team)
            except Exception:
                logger.exception("Score recalculation failed for team %s", team.id)
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(
        sync_all_teams_job,
        "interval",
        minutes=settings.GITHUB_SYNC_INTERVAL_MINUTES,
        id="github_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        recalc_all_scores_job,
        "interval",
        minutes=settings.SCORE_RECALC_INTERVAL_MINUTES,
        id="score_recalc",
        replace_existing=True,
    )
    scheduler.start()
