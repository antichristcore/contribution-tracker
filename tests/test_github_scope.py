"""GitHub-логин принадлежит человеку, а не его участию в проекте.

Регрессия на реальный баг: у тимлида семь проектов, в каждом отдельная строка
участника, и логин сохранялся только в текущем. При переключении проекта
блокирующий экран появлялся снова — со стороны это выглядит как «логин не
сохраняется вообще».
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.deps import get_current_member, get_db
from backend.app.main import app
from backend.app.models import GithubMapping, Member, SystemRole
from backend.app.services import github_identity
from backend.app.services.team_membership import (
    create_team,
    join_team_by_code,
    known_github_username,
    propagate_github_username,
)
from tests.conftest import make_member, make_team

TG_ID = 700700


def member_in(db, team, *, github=None, system_role=SystemRole.member) -> Member:
    m = make_member(db, team, name="Марина", system_role=system_role, with_github=False)
    m.telegram_user_id = TG_ID
    if github:
        db.add(GithubMapping(member_id=m.id, github_username=github))
    db.commit()
    db.refresh(m)
    return m


def test_known_username_is_found_across_projects(db, team):
    other = make_team(db, name="Второй проект")
    member_in(db, team, github="marina")
    member_in(db, other)

    assert known_github_username(db, TG_ID) == "marina"


def test_known_username_is_none_for_a_stranger(db, team):
    member_in(db, team, github="marina")

    assert known_github_username(db, 111222) is None


def test_propagation_fills_every_project_without_a_login(db, team):
    second = make_team(db, name="Второй")
    third = make_team(db, name="Третий")
    member_in(db, team, github="marina")
    b = member_in(db, second)
    c = member_in(db, third)

    touched = propagate_github_username(db, TG_ID, "marina")
    db.commit()

    assert set(touched) == {second.id, third.id}
    assert b.github_mapping.github_username == "marina"
    assert c.github_mapping.github_username == "marina"


def test_propagation_does_not_overwrite_a_deliberate_other_account(db, team):
    """В другом проекте человек мог сознательно указать второй аккаунт."""
    second = make_team(db, name="Второй")
    member_in(db, team, github="marina")
    b = member_in(db, second, github="marina-work")

    propagate_github_username(db, TG_ID, "marina")
    db.commit()

    assert b.github_mapping.github_username == "marina-work"


def test_new_project_inherits_the_login(db, team):
    member_in(db, team, github="marina")

    new_team, new_member = create_team(db, "Ещё один", TG_ID, "marina_tg", "Марина")

    assert new_member.github_mapping is not None
    assert new_member.github_mapping.github_username == "marina"


def test_joining_by_code_inherits_the_login(db, team):
    member_in(db, team, github="marina")
    other = make_team(db, name="Чужой проект", code="JOINME1")

    _, joined = join_team_by_code(db, "JOINME1", TG_ID, "marina_tg", "Марина")

    assert joined.team_id == other.id
    assert joined.github_mapping.github_username == "marina"


@pytest.fixture
def client(db, team, monkeypatch):
    lead = member_in(db, team, system_role=SystemRole.teamlead)

    async def fake(login, token=None):
        return {"login": login, "name": None, "avatar_url": None}

    monkeypatch.setattr(github_identity, "fetch_github_user", fake)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_member] = lambda: lead
    yield TestClient(app), lead
    app.dependency_overrides.clear()


def test_saving_the_login_once_covers_the_other_projects(client, db, team):
    """Тот самый сценарий: сохранил в одном проекте — в остальных тоже есть."""
    api, lead = client
    second = make_team(db, name="Второй")
    elsewhere = member_in(db, second)

    r = api.patch(f"/api/members/{lead.id}", json={"github_username": "marina"})

    assert r.status_code == 200
    db.refresh(elsewhere)
    assert elsewhere.github_mapping is not None
    assert elsewhere.github_mapping.github_username == "marina"
