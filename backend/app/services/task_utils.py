from sqlalchemy.orm import Session

from backend.app.models import Commit, Member, Task, TaskStatus, Team
from backend.app.schemas import CommitOut, TaskOut
from backend.app.utils.time import utcnow


def task_to_out(db: Session, task: Task) -> TaskOut:
    stuck_days = 0
    if task.status != TaskStatus.done:
        stuck_days = max((utcnow() - task.status_changed_at).days, 0)
    linked_commits_count = db.query(Commit).filter(Commit.task_id == task.id).count()
    return TaskOut(
        id=task.id,
        number=task.number,
        title=task.title,
        description=task.description,
        assignee_member_id=task.assignee_member_id,
        assignee_name=task.assignee.display_name if task.assignee else None,
        created_by_member_id=task.created_by_member_id,
        status=task.status,
        deadline_at=task.deadline_at,
        status_changed_at=task.status_changed_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        stuck_days=stuck_days,
        linked_commits_count=linked_commits_count,
    )


def member_names(db: Session, member_ids: set[int]) -> dict[int, str]:
    ids = {m for m in member_ids if m}
    if not ids:
        return {}
    return dict(db.query(Member.id, Member.display_name).filter(Member.id.in_(ids)).all())


def commit_url(team: Team | None, sha: str) -> str | None:
    """Link to the commit on GitHub. None when the team has no repo connected
    (synthetic demo data, for one) — the UI then renders a plain row instead of
    a link that would 404."""
    if not team or not team.github_owner or not team.github_repo:
        return None
    return f"https://github.com/{team.github_owner}/{team.github_repo}/commit/{sha}"


def task_numbers(db: Session, task_ids: set[int]) -> dict[int, int]:
    ids = {t for t in task_ids if t}
    if not ids:
        return {}
    return dict(db.query(Task.id, Task.number).filter(Task.id.in_(ids)).all())


def commits_to_out(db: Session, commits: list[Commit], team: Team | None = None) -> list[CommitOut]:
    """Commits with a human author name — the resolved team member when we
    know them, otherwise whatever git recorded."""
    names = member_names(db, {c.member_id for c in commits})
    numbers = task_numbers(db, {c.task_id for c in commits})
    return [
        CommitOut(
            id=c.id,
            sha=c.sha,
            message=c.message,
            authored_at=c.authored_at,
            additions=c.additions,
            deletions=c.deletions,
            author_name=names.get(c.member_id) or c.raw_author_name or c.raw_author_login,
            html_url=commit_url(team, c.sha),
            task_number=numbers.get(c.task_id),
        )
        for c in commits
    ]
