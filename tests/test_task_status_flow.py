"""Вывод статуса задачи из коммитов: advance_task_status + relink_unlinked_commits.

Дополняет test_task_linking.py, который проверяет только разбор ссылки и
выбор задачи. Здесь — что происходит с самой задачей после привязки.

Оба покрытых здесь правила появились как исправления реальных багов:
  - коммит закрывал задачу по ключевому слову, и «fix #42» в смысле «работаю
    над этим» мгновенно уводил её в «готово»; теперь закрывает только человек;
  - status_changed_at двигался только при переходе todo -> in_progress,
    поэтому счётчик «N дней без изменений» врал на активных задачах.
"""

from datetime import timedelta

import pytest

from backend.app.models import Commit, TaskStatus, TaskStatusHistory
from backend.app.services.task_linking import (
    advance_task_status,
    parse_task_references,
    relink_unlinked_commits,
)
from tests.conftest import NOW, make_commit, make_member, make_task


# --- переходы статуса ---------------------------------------------------------


def test_first_commit_starts_a_todo_task(db, team):
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, status=TaskStatus.todo)

    advance_task_status(db, task, NOW)

    assert task.status is TaskStatus.in_progress
    assert task.completed_at is None


@pytest.mark.parametrize(
    "message", ["Fix login bug #{n}", "fixes #{n}", "closes #{n}", "готово #{n}"]
)
def test_no_commit_ever_completes_a_task(db, team, message):
    """Регрессия: коммит закрывал задачу по ключевому слову. Теперь любое
    сообщение — только привязка, «готово» ставит человек."""
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, status=TaskStatus.in_progress)

    assert parse_task_references(message.format(n=task.id)) == [task.id]
    advance_task_status(db, task, NOW)

    assert task.status is TaskStatus.in_progress
    assert task.completed_at is None


def test_done_task_is_never_reopened(db, team):
    """Правило «только вперёд»: доработка после закрытия не воскрешает задачу."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.done, created_days_ago=10, completed_days_ago=2
    )
    completed_at = task.completed_at

    advance_task_status(db, task, NOW)

    assert task.status is TaskStatus.done
    assert task.completed_at == completed_at


# --- счётчик застоя -----------------------------------------------------------


def test_every_commit_moves_the_staleness_clock(db, team):
    """Регрессия: «N дней без изменений» считалось от первого коммита, а не
    от последнего, и активная задача выглядела заброшенной."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.in_progress,
        created_days_ago=20, status_changed_days_ago=9,
    )
    assert (NOW - task.status_changed_at).days == 9

    advance_task_status(db, task, NOW)

    assert task.status_changed_at == NOW


def test_older_commit_does_not_rewind_the_clock(db, team):
    """Синк приходит пачкой и не по порядку — старый коммит не должен
    состарить задачу, по которой уже был свежий."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.in_progress, status_changed_days_ago=0
    )

    advance_task_status(db, task, NOW - timedelta(days=5))

    assert task.status_changed_at == NOW


def test_status_change_is_recorded_as_automatic(db, team):
    """Переход, выведенный из коммита, пишется в историю без автора —
    в карточке он показывается как «автоматически»."""
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, status=TaskStatus.todo)

    advance_task_status(db, task, NOW)
    db.commit()

    rows = db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id == task.id).all()
    assert len(rows) == 1
    assert rows[0].old_status is TaskStatus.todo
    assert rows[0].new_status is TaskStatus.in_progress
    assert rows[0].changed_by_member_id is None


def test_timestamp_only_move_writes_no_history(db, team):
    """Второй коммит по уже начатой задаче двигает время, но не плодит
    одинаковые записи «в работе -> в работе» в истории."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.in_progress, status_changed_days_ago=3
    )

    advance_task_status(db, task, NOW)
    db.commit()

    assert db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id == task.id).count() == 0
    assert task.status_changed_at == NOW


# --- дозачистка после синка ---------------------------------------------------


def test_relink_picks_up_commits_that_arrived_before_the_task(db, team):
    """Коммит синкнулся раньше, чем тимлид завёл задачу с этим номером."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.todo,
        created_days_ago=2, status_changed_days_ago=2,
    )
    orphan = make_commit(db, team, member, days_ago=1, message=f"работа по #{task.id}")

    linked = relink_unlinked_commits(db, team.id)
    db.commit()

    assert linked == 1
    assert db.get(Commit, orphan.id).task_id == task.id
    assert task.status is TaskStatus.in_progress


def test_relink_is_idempotent(db, team):
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.todo,
        created_days_ago=2, status_changed_days_ago=2,
    )
    make_commit(db, team, member, days_ago=1, message=f"#{task.id}")

    assert relink_unlinked_commits(db, team.id) == 1
    db.commit()
    assert relink_unlinked_commits(db, team.id) == 0


def test_commits_without_references_stay_unlinked(db, team):
    member = make_member(db, team)
    make_task(db, team, assignee=member)
    c = make_commit(db, team, member, message="просто рефакторинг")

    assert relink_unlinked_commits(db, team.id) == 0
    assert db.get(Commit, c.id).task_id is None


def test_relink_applies_commits_in_chronological_order(db, team):
    """Синк приходит пачкой и не по порядку. Коммиты применяются от старого к
    новому, поэтому счётчик застоя встаёт на самый свежий из них."""
    member = make_member(db, team)
    task = make_task(
        db, team, assignee=member, status=TaskStatus.todo,
        created_days_ago=5, status_changed_days_ago=5,
    )
    make_commit(db, team, member, days_ago=1, message=f"доделал #{task.id}")
    make_commit(db, team, member, days_ago=3, message=f"начал #{task.id}")

    assert relink_unlinked_commits(db, team.id) == 2
    db.commit()

    assert task.status is TaskStatus.in_progress
    assert task.status_changed_at == NOW - timedelta(days=1)
