from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.deps import get_current_member, get_db, require_teamlead
from backend.app.models import Commit, Member, SystemRole, Task, TaskStatus, TaskStatusHistory, Team
from backend.app.schemas import CommitOut, TaskCreate, TaskDetailOut, TaskHistoryOut, TaskOut, TaskUpdate
from backend.app.services.notifications import notify_task_assigned_by_id
from backend.app.services.task_linking import advance_task_status
from backend.app.services.task_numbers import next_task_number
from backend.app.services.task_utils import commits_to_out, member_names, task_to_out, utcnow

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CommitLinkIn(BaseModel):
    commit_ids: list[int]


def _get_team_task(db: Session, task_id: int, current: Member) -> Task:
    task = db.get(Task, task_id)
    if not task or task.team_id != current.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def _require_editor(task: Task, current: Member) -> None:
    """Attaching/detaching commits and completing a task is for the teamlead
    or the person the task is assigned to — not any teammate who can see the
    board."""
    if current.system_role != SystemRole.teamlead and task.assignee_member_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")


def _task_detail(db: Session, task: Task) -> TaskDetailOut:
    commits = (
        db.query(Commit).filter(Commit.task_id == task.id).order_by(Commit.authored_at.desc()).all()
    )
    history = (
        db.query(TaskStatusHistory)
        .filter(TaskStatusHistory.task_id == task.id)
        .order_by(TaskStatusHistory.changed_at.asc())
        .all()
    )
    names = member_names(db, {h.changed_by_member_id for h in history})
    return TaskDetailOut(
        task=task_to_out(db, task),
        commits=commits_to_out(db, commits, db.get(Team, task.team_id)),
        history=[
            TaskHistoryOut(
                old_status=h.old_status,
                new_status=h.new_status,
                changed_at=h.changed_at,
                changed_by_name=names.get(h.changed_by_member_id),
            )
            for h in history
        ],
    )


@router.get("", response_model=list[TaskOut])
def list_tasks(
    assignee_id: int | None = None,
    status_filter: TaskStatus | None = None,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> list[TaskOut]:
    # The board is shared: every team member sees all of the team's tasks.
    query = db.query(Task).filter(Task.team_id == current.team_id)
    if assignee_id is not None:
        query = query.filter(Task.assignee_member_id == assignee_id)
    if status_filter is not None:
        query = query.filter(Task.status == status_filter)
    tasks = query.order_by(Task.created_at.desc()).all()
    return [task_to_out(db, t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> TaskOut:
    task = Task(
        team_id=teamlead.team_id,
        number=next_task_number(db, teamlead.team_id),
        title=payload.title,
        description=payload.description,
        assignee_member_id=payload.assignee_member_id,
        created_by_member_id=teamlead.id,
        deadline_at=payload.deadline_at,
        status=TaskStatus.todo,
    )
    db.add(task)
    db.flush()
    db.add(TaskStatusHistory(task_id=task.id, old_status=None, new_status=TaskStatus.todo, changed_by_member_id=teamlead.id))
    db.commit()
    db.refresh(task)

    background_tasks.add_task(notify_task_assigned_by_id, task.id)
    return task_to_out(db, task)


@router.get("/{task_id}", response_model=TaskDetailOut)
def get_task(
    task_id: int, db: Session = Depends(get_db), current: Member = Depends(get_current_member)
) -> TaskDetailOut:
    return _task_detail(db, _get_team_task(db, task_id, current))


@router.get("/{task_id}/link-candidates", response_model=list[CommitOut])
def link_candidates(
    task_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> list[CommitOut]:
    """Team commits not attached to any task yet — the fallback for when
    someone forgot to put #<id> in the commit message."""
    task = _get_team_task(db, task_id, current)
    _require_editor(task, current)
    commits = (
        db.query(Commit)
        .filter(Commit.team_id == current.team_id, Commit.task_id.is_(None))
        .order_by(Commit.authored_at.desc())
        .limit(limit)
        .all()
    )
    return commits_to_out(db, commits, db.get(Team, current.team_id))


@router.post("/{task_id}/commits", response_model=TaskDetailOut)
def attach_commits(
    task_id: int,
    payload: CommitLinkIn,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> TaskDetailOut:
    task = _get_team_task(db, task_id, current)
    _require_editor(task, current)

    commits = (
        db.query(Commit)
        .filter(Commit.id.in_(payload.commit_ids), Commit.team_id == current.team_id)
        .order_by(Commit.authored_at.asc())
        .all()
    )
    for commit in commits:
        commit.task_id = task.id
        # Привязка — что руками, что по «#номер» — только начинает задачу.
        # Закрыть её может только человек кнопкой «Отметить готовой».
        advance_task_status(db, task, commit.authored_at)

    db.commit()
    db.refresh(task)
    return _task_detail(db, task)


@router.delete("/{task_id}/commits/{commit_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_commit(
    task_id: int,
    commit_id: int,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> None:
    task = _get_team_task(db, task_id, current)
    _require_editor(task, current)

    commit = db.get(Commit, commit_id)
    if not commit or commit.team_id != current.team_id or commit.task_id != task.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commit not found")
    commit.task_id = None
    db.commit()


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> TaskOut:
    task = _get_team_task(db, task_id, current)

    is_teamlead = current.system_role == SystemRole.teamlead
    _require_editor(task, current)

    if not is_teamlead:
        if any(
            getattr(payload, field) is not None
            for field in ("title", "description", "assignee_member_id", "deadline_at")
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the teamlead can edit task details")
        # The only self-service status change is marking work done by hand
        # (fallback for tasks that produce no commits, e.g. design). Starting
        # a task is derived from linked commits, not self-reported.
        if payload.status is not None and payload.status != TaskStatus.done:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Status is tracked automatically from commits")

    if is_teamlead:
        if payload.title is not None:
            task.title = payload.title
        if payload.description is not None:
            task.description = payload.description
        if payload.assignee_member_id is not None and payload.assignee_member_id != task.assignee_member_id:
            task.assignee_member_id = payload.assignee_member_id
            background_tasks.add_task(notify_task_assigned_by_id, task.id)
        # Через model_fields_set, а не "is not None": иначе явный null нельзя
        # отличить от «поле не передали», и снять дедлайн становится нечем.
        if "deadline_at" in payload.model_fields_set:
            task.deadline_at = payload.deadline_at

    if payload.status is not None and payload.status != task.status:
        old_status = task.status
        task.status = payload.status
        task.status_changed_at = utcnow()
        if payload.status == TaskStatus.done:
            task.completed_at = utcnow()
        db.add(
            TaskStatusHistory(
                task_id=task.id,
                old_status=old_status,
                new_status=payload.status,
                changed_by_member_id=current.id,
            )
        )

    db.commit()
    db.refresh(task)
    return task_to_out(db, task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int, db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> None:
    task = _get_team_task(db, task_id, teamlead)
    # SQLite doesn't enforce foreign keys here, so clean up by hand instead of
    # leaving commits pointing at a task that no longer exists.
    db.query(Commit).filter(Commit.task_id == task.id).update({Commit.task_id: None}, synchronize_session=False)
    db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
