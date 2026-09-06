"""Флаг «нужен GitHub-логин» в /api/bootstrap.

Он решает, увидит ли человек доску или блокирующий экран, и едет тем же
запросом, что и всё остальное — отдельный round-trip на старте стоит дорого
(через туннель это ~400 мс до первой отрисовки).
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.deps import TelegramUser, get_current_telegram_user, get_db
from backend.app.main import app
from backend.app.models import GithubMapping, Member, SystemRole
from tests.conftest import make_member

TG_ID = 900001


@pytest.fixture
def client(db, team):
    """Клиент, авторизованный как конкретный telegram-пользователь."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_telegram_user] = lambda: TelegramUser(
        telegram_user_id=TG_ID, username="tester", first_name="Тестер"
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def join(db, team, *, with_github: bool, system_role=SystemRole.member) -> Member:
    member = make_member(db, team, name="Тестер", system_role=system_role, with_github=with_github)
    member.telegram_user_id = TG_ID
    db.commit()
    db.refresh(member)
    return member


def test_member_without_github_is_gated(client, db, team):
    join(db, team, with_github=False)

    body = client.get(f"/api/bootstrap?team_id={team.id}").json()

    assert body["member"] is not None
    assert body["needs_github_username"] is True


def test_member_with_github_goes_straight_to_the_board(client, db, team):
    join(db, team, with_github=True)

    body = client.get(f"/api/bootstrap?team_id={team.id}").json()

    assert body["needs_github_username"] is False
    assert body["tasks"] is not None


def test_teamlead_is_gated_too(client, db, team):
    """Правило одно для всех: тимлид тоже коммитит, и его коммиты не должны
    оставаться ничьими."""
    join(db, team, with_github=False, system_role=SystemRole.teamlead)

    body = client.get(f"/api/bootstrap?team_id={team.id}").json()

    assert body["needs_github_username"] is True


def test_empty_username_counts_as_missing(client, db, team):
    """Пустая строка в маппинге — то же самое, что его отсутствие: строка
    могла остаться от старой формы, где логин был необязательным."""
    member = join(db, team, with_github=False)
    db.add(GithubMapping(member_id=member.id, github_username=""))
    db.commit()

    body = client.get(f"/api/bootstrap?team_id={team.id}").json()

    assert body["needs_github_username"] is True
