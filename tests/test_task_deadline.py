"""Перенос и снятие срока задачи (PATCH /tasks/{id}).

Раньше дедлайн применялся через "is not None", поэтому явный null нельзя было
отличить от «поле не передали» — снять срок было нечем.
"""

from datetime import timedelta

from backend.app.models import SystemRole
from backend.app.routers.tasks import update_task
from backend.app.schemas import TaskUpdate
from tests.conftest import NOW, make_member, make_task


class _Bg:
    """Заглушка BackgroundTasks: уведомления в тесте не шлём."""

    def add_task(self, *args, **kwargs):
        pass


def _lead(db, team):
    return make_member(db, team, name="Lead", system_role=SystemRole.teamlead)


def test_teamlead_moves_the_deadline(db, team):
    lead = _lead(db, team)
    member = make_member(db, team, name="Аня")
    task = make_task(db, team, assignee=member, deadline_days_ago=-1)
    new_deadline = NOW + timedelta(days=10)

    update_task(task.id, TaskUpdate(deadline_at=new_deadline), _Bg(), db, lead)

    assert task.deadline_at == new_deadline


def test_teamlead_clears_the_deadline(db, team):
    lead = _lead(db, team)
    member = make_member(db, team, name="Аня")
    task = make_task(db, team, assignee=member, deadline_days_ago=-3)
    assert task.deadline_at is not None

    update_task(task.id, TaskUpdate(deadline_at=None), _Bg(), db, lead)

    assert task.deadline_at is None


def test_omitting_the_field_leaves_the_deadline_alone(db, team):
    """Правка только названия не должна сбрасывать срок."""
    lead = _lead(db, team)
    member = make_member(db, team, name="Аня")
    task = make_task(db, team, assignee=member, deadline_days_ago=-5)
    before = task.deadline_at

    update_task(task.id, TaskUpdate(title="Новое название"), _Bg(), db, lead)

    assert task.title == "Новое название"
    assert task.deadline_at == before


def test_member_cannot_move_the_deadline(db, team):
    """Срок — обязательство перед командой, двигает его тимлид."""
    import pytest
    from fastapi import HTTPException

    member = make_member(db, team, name="Аня")
    task = make_task(db, team, assignee=member, deadline_days_ago=-2)
    before = task.deadline_at

    with pytest.raises(HTTPException) as exc:
        update_task(task.id, TaskUpdate(deadline_at=NOW + timedelta(days=30)), _Bg(), db, member)

    assert exc.value.status_code == 403
    assert task.deadline_at == before
