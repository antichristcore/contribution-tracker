"""Нумерация задач внутри проекта.

`Task.id` — сквозной по всей базе, поэтому у второго проекта задачи
начинались бы с «#46». Человек пишет номер в сообщении коммита, значит номер
должен быть коротким и своим у каждого проекта.
"""

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from backend.app.models import Task


def next_task_number(db: Session, team_id: int) -> int:
    """Следующий свободный номер в проекте. Номера не переиспользуются после
    удаления: иначе старый коммит с «#3» привязался бы к новой задаче."""
    current = db.query(func.max(Task.number)).filter(Task.team_id == team_id).scalar()
    return (current or 0) + 1


def ensure_task_numbers(engine) -> None:
    """Досоздаёт колонку и проставляет номера уже существующим задачам.

    Alembic в проекте нет, а `create_all` не умеет добавлять колонки в готовую
    таблицу — поэтому маленькая идемпотентная миграция прямо на старте.
    """
    columns = {c["name"] for c in inspect(engine).get_columns("tasks")}
    if "number" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN number INTEGER NOT NULL DEFAULT 0"))
        # Нумеруем в порядке создания, отдельно по каждому проекту.
        rows = conn.execute(text("SELECT id, team_id FROM tasks ORDER BY team_id, created_at, id")).fetchall()
        counters: dict[int, int] = {}
        for task_id, team_id in rows:
            counters[team_id] = counters.get(team_id, 0) + 1
            conn.execute(
                text("UPDATE tasks SET number = :n WHERE id = :id"),
                {"n": counters[team_id], "id": task_id},
            )
        conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_task_team_number ON tasks (team_id, number)")
        )
