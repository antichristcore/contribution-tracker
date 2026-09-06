"""Разовый переход на шкалу вклада 0..100.

В `score_history` лежат значения старой шкалы (−0.15..1.35). Смешивать их с
новыми нельзя: на графике «Динамика команды» это выглядит как обвал, а серии
«ниже медианы N дней подряд» считаются по обеим шкалам сразу и врут.

История — производные данные, поэтому она стирается и считается заново.
Демо-команде 21 день перепишет сидер, живым командам — планировщик.

Запуск (из корня проекта):
    .venv\\Scripts\\python.exe scripts\\migrate_score_scale.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Консоль Windows живёт в cp1251 и падает на невидимых символах в названиях
# проектов (их туда заносит копипаст из Telegram). Отчёт скрипта не повод
# ронять миграцию.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.app.db import SessionLocal  # noqa: E402
from backend.app.models import ScoreHistory, Team  # noqa: E402
from backend.app.services.recalc import recalculate_team_scores  # noqa: E402


async def main() -> None:
    db = SessionLocal()
    try:
        removed = db.query(ScoreHistory).delete(synchronize_session=False)
        db.commit()
        print(f"Удалено строк истории на старой шкале: {removed}")

        teams = db.query(Team).all()
        for team in teams:
            summary = await recalculate_team_scores(db, team)
            scored = [f"{row['display_name']}: {row['score']}" for row in summary]
            print(f"[{team.name}] {', '.join(scored) if scored else 'нет участников'}")
    finally:
        db.close()

    print("Готово. Дальше история копится сама — планировщиком и кнопкой «Обновить».")


if __name__ == "__main__":
    asyncio.run(main())
