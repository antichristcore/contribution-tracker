"""Links GitHub commits to tasks by parsing "#<номер>" references out of commit
messages. This is what drives task status from real commit activity instead of
a self-reported status button."""

import re
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models import Commit, Task, TaskStatus, TaskStatusHistory

# Ссылка «#42» только привязывает коммит к задаче и переводит её в «в работе».
# Ключевых слов вроде «fixes» здесь сознательно нет: люди пишут «fix #42» в
# смысле «работаю над этим», и задача закрывалась сама на первом же коммите.
# Закрыть задачу может только человек — кнопкой «Отметить готовой».
_REF_RE = re.compile(r"#(?P<number>\d+)")


def parse_task_references(message: str | None) -> list[int]:
    """Номера задач в порядке появления в сообщении."""
    if not message:
        return []
    return [int(m.group("number")) for m in _REF_RE.finditer(message)]


def link_commit_to_task(
    db: Session, team_id: int, message: str | None, authored_at: datetime
) -> Task | None:
    """First referenced task belonging to this team."""
    for number in parse_task_references(message):
        # Ищем по номеру внутри проекта: "#3" у разных команд — разные задачи.
        task = (
            db.query(Task).filter(Task.team_id == team_id, Task.number == number).first()
        )
        # Коммит, написанный до создания задачи, не может быть работой по ней —
        # этот же guard гасит ложные срабатывания на номерах GitHub-issue из
        # старой истории репозитория.
        if task and authored_at >= task.created_at:
            return task
    return None


def advance_task_status(db: Session, task: Task, authored_at: datetime) -> None:
    """Forward-only. Every linked commit pushes status_changed_at forward, so
    "no changes for N days" means "N days since the last commit on this task";
    the first commit starts the task. Коммит никогда не закрывает задачу и
    никогда не переоткрывает закрытую."""
    if task.status == TaskStatus.done:
        return

    if task.status_changed_at is None or authored_at > task.status_changed_at:
        task.status_changed_at = authored_at

    if task.status != TaskStatus.todo:
        return  # уже в работе — сдвинулось только время активности

    old_status = task.status
    task.status = TaskStatus.in_progress
    db.add(
        TaskStatusHistory(
            task_id=task.id,
            old_status=old_status,
            new_status=task.status,
            changed_by_member_id=None,
        )
    )


def relink_unlinked_commits(db: Session, team_id: int) -> int:
    """Attach every still-unlinked commit whose message references a task,
    oldest first so the staleness clock ends up on the newest commit. Runs
    after each sync, which also picks up commits that arrived before their
    task existed."""
    commits = (
        db.query(Commit)
        .filter(Commit.team_id == team_id, Commit.task_id.is_(None))
        .order_by(Commit.authored_at.asc())
        .all()
    )

    linked = 0
    for commit in commits:
        task = link_commit_to_task(db, team_id, commit.message, commit.authored_at)
        if not task:
            continue
        commit.task_id = task.id
        advance_task_status(db, task, commit.authored_at)
        linked += 1
    return linked
