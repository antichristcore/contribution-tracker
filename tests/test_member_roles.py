"""Смена ролей участника: PATCH /api/members/{id}.

Ключевое здесь — гард на последнего тимлида. Разжаловать самого себя, будучи
единственным тимлидом, значит остаться с проектом, в котором некому создать
задачу, позвать человека или поменять настройки. Откатить это из интерфейса
уже нельзя.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.deps import get_current_member, get_db
from backend.app.main import app
from backend.app.models import SystemRole
from backend.app.services import github_identity
from tests.conftest import make_member


@pytest.fixture
def client(db, team, monkeypatch):
    """Клиент, работающий от имени тимлида этой команды."""
    teamlead = make_member(db, team, name="Марина", role="pm", system_role=SystemRole.teamlead)

    async def fake_github(login, token=None):
        return {"login": login, "name": None, "avatar_url": None}

    monkeypatch.setattr(github_identity, "fetch_github_user", fake_github)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_member] = lambda: teamlead
    yield TestClient(app), teamlead
    app.dependency_overrides.clear()


def test_teamlead_can_change_a_working_role(client, db, team):
    api, _ = client
    member = make_member(db, team, name="Аня", role="backend")

    r = api.patch(f"/api/members/{member.id}", json={"role_in_team": "design"})

    assert r.status_code == 200
    assert r.json()["role_in_team"] == "design"


def test_teamlead_can_promote_a_member(client, db, team):
    api, _ = client
    member = make_member(db, team, name="Аня", role="backend")

    r = api.patch(f"/api/members/{member.id}", json={"system_role": "teamlead"})

    assert r.status_code == 200
    assert r.json()["system_role"] == "teamlead"


def test_last_teamlead_cannot_be_demoted(client):
    api, teamlead = client

    r = api.patch(f"/api/members/{teamlead.id}", json={"system_role": "member"})

    assert r.status_code == 400
    assert "тимлид" in r.json()["detail"].lower()


def test_teamlead_can_step_down_once_someone_else_leads(client, db, team):
    api, teamlead = client
    make_member(db, team, name="Новый лид", role="pm", system_role=SystemRole.teamlead)

    r = api.patch(f"/api/members/{teamlead.id}", json={"system_role": "member"})

    assert r.status_code == 200
    assert r.json()["system_role"] == "member"


def test_github_username_is_verified_before_saving(client, db, team, monkeypatch):
    api, _ = client
    member = make_member(db, team, name="Аня", role="backend")

    async def not_found(login, token=None):
        return None

    monkeypatch.setattr(github_identity, "fetch_github_user", not_found)

    r = api.patch(f"/api/members/{member.id}", json={"github_username": "nosuchuser"})

    assert r.status_code == 400
    assert "nosuchuser" in r.json()["detail"]
