"""Links GitHub commits to tasks by parsing "#<id>" references out of commit
messages — the same convention GitHub/Jira "smart commits" use. This is what
drives task status from real commit activity instead of a self-reported
status button."""

import re
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models import Commit, Task, TaskStatus, TaskStatusHistory

# A bare "#42" links a commit to task 42. A closing keyword *immediately
# before* the reference ("fixes #42") also completes it — matching GitHub's
# own semantics, so an ordinary "Fix login bug #42" links without silently
# closing the task.
_REF_RE = re.compile(
    r"(?:(?P<kw>close[sd]?|fix(?:e[sd])?|resolve[sd]?|закрывает|готово)\s+)?#(?P<id>\d+)",
    re.IGNORECASE,
)


def parse_task_references(message: str | None) -> list[tuple[int, bool]]:
    """[(task_id, is_closing), ...] in the order they appear in the message."""
    if not message:
        return []
    return [(int(m.group("id")), bool(m.group("kw"))) for m in _REF_RE.finditer(message)]


def link_commit_to_task(
    db: Session, team_id: int, message: str | None, authored_at: datetime
) -> tuple[Task, bool] | None:
    """First referenced task belonging to this team, plus whether the
    reference was a closing one."""
    for task_id, is_closing in parse_task_references(message):
        task = db.get(Task, task_id)
        # Task ids are global, so a reference must be checked against the
        # team. A commit written before the task existed can't be work for
        # it either — that guard also kills false positives on GitHub issue
        # numbers from older history.
        if task and task.team_id == team_id and authored_at >= task.created_at:
            return task, is_closing
    return None


def advance_task_status(db: Session, task: Task, authored_at: datetime, is_closing: bool) -> None:
    """Forward-only. Every linked commit pushes status_changed_at forward, so
    "no changes for N days" means "N days since the last commit on this task";
    a closing keyword completes the task; the first commit starts it. A done
    task is never reopened."""
    if task.status == TaskStatus.done:
        return

    if task.status_changed_at is None or authored_at > task.status_changed_at:
        task.status_changed_at = authored_at

    old_status = task.status
    if is_closing:
        task.status = TaskStatus.done
        task.completed_at = authored_at
    elif task.status == TaskStatus.todo:
        task.status = TaskStatus.in_progress
    else:
        return  # already in progress — only the activity timestamp moved

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
    oldest first so status transitions land in chronological order. Runs after
    each sync, which also picks up commits that arrived before their task
    existed."""
    commits = (
        db.query(Commit)
        .filter(Commit.team_id == team_id, Commit.task_id.is_(None))
        .order_by(Commit.authored_at.asc())
        .all()
    )

    linked = 0
    for commit in commits:
        result = link_commit_to_task(db, team_id, commit.message, commit.authored_at)
        if not result:
            continue
        task, is_closing = result
        commit.task_id = task.id
        advance_task_status(db, task, commit.authored_at, is_closing)
        linked += 1
    return linked
