"""Нумерация задач внутри проекта.

`Task.id` сквозной по всей базе, поэтому у второго проекта задачи начинались
с «#46». Номер, который человек пишет в коммите, должен быть своим у каждого
проекта и начинаться с единицы.
"""

from backend.app.models import TaskStatus
from backend.app.services.task_linking import link_commit_to_task
from backend.app.services.task_numbers import next_task_number
from tests.conftest import NOW, make_member, make_task, make_team


def test_numbering_starts_at_one(db, team):
    member = make_member(db, team)
    first = make_task(db, team, assignee=member, title="Первая")
    second = make_task(db, team, assignee=member, title="Вторая")

    assert first.number == 1
    assert second.number == 2


def test_new_project_starts_over_from_one(db, team):
    """Главное в этом баге: id уже ушёл далеко, а номер обязан начаться заново."""
    make_task(db, team, assignee=make_member(db, team))
    make_task(db, team, assignee=make_member(db, team, name="Второй"))

    other = make_team(db, name="Второй проект")
    fresh = make_task(db, other, assignee=make_member(db, other, name="Новичок"))

    assert fresh.number == 1
    assert fresh.id > 1, "id сквозной — иначе тест ничего не проверяет"


def test_same_number_in_two_projects_are_different_tasks(db, team):
    """«#1» у разных команд — разные задачи, и коммит не должен их путать."""
    mine = make_task(db, team, assignee=make_member(db, team), title="Моя")

    other = make_team(db, name="Чужой проект")
    theirs = make_task(db, other, assignee=make_member(db, other, name="Чужой"), title="Чужая")

    assert mine.number == theirs.number == 1

    linked = link_commit_to_task(db, team.id, "работа по #1", NOW)
    assert linked is not None
    assert linked.id == mine.id
    assert linked.id != theirs.id


def test_commit_reference_resolves_by_number_not_id(db, team):
    """Ссылка «#1» ведёт на первую задачу проекта, а не на задачу с id=1."""
    other = make_team(db, name="Чужой проект")
    make_task(db, other, assignee=make_member(db, other, name="Чужой"))  # займёт id=1

    member = make_member(db, team)
    mine = make_task(db, team, assignee=member, title="Моя первая")
    assert mine.number == 1
    assert mine.id != 1

    linked = link_commit_to_task(db, team.id, "работа по #1", NOW)
    assert linked is not None
    assert linked.id == mine.id


def test_number_is_reused_after_deleting_the_last_task(db, team):
    """Номер считается как max+1, поэтому после удаления последней задачи он
    освобождается. Осознанный компромисс: отдельный счётчик на проект стоил бы
    ещё одной колонки, а от неверной привязки защищает guard по дате — коммит,
    написанный раньше создания задачи, к ней не цепляется."""
    member = make_member(db, team)
    make_task(db, team, assignee=member, title="Первая")
    second = make_task(db, team, assignee=member, title="Вторая")
    assert second.number == 2

    db.delete(second)
    db.commit()

    assert next_task_number(db, team.id) == 2


def test_unknown_number_does_not_link(db, team):
    make_task(db, team, assignee=make_member(db, team), status=TaskStatus.todo)
    assert link_commit_to_task(db, team.id, "работа по #999", NOW) is None
