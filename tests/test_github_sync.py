"""Синхронизация с GitHub: _sync_commits_and_reviews.

Регрессия на реальный баг: в ответе возвращалась переменная, которую никто не
присваивал. Падало на самой последней строке, уже после db.commit(), поэтому
данные сохранялись, а участник видел «GitHub: name 'rematched' is not defined»
и думал, что синк не работает. Заодно молча не выполнялось сопоставление
авторов, ради которого эта переменная и была.

Клиент здесь подставной: настоящий GitHub в тестах не нужен, а проверяем мы
свою обработку ответа, а не чужой API.
"""

import asyncio

import pytest

from backend.app.models import Commit, GithubMapping
from backend.app.services.github_sync_service import _sync_commits_and_reviews
from tests.conftest import NOW, make_member, make_task, make_team


class FakeGitHub:
    """Отдаёт ровно то, что просят, и запоминает, о чём спрашивали."""

    def __init__(self, commits=None, pulls=None, reviews=None):
        self._commits = commits or []
        self._pulls = pulls or []
        self._reviews = reviews or {}

    async def list_commits(self, since=None):
        return self._commits

    async def get_commit(self, sha):
        return {"stats": {"additions": 10, "deletions": 2}}

    async def list_recent_pull_requests(self, state="all", limit=30):
        return self._pulls

    async def list_pr_reviews(self, pr_number):
        return self._reviews.get(pr_number, [])


def commit_payload(sha, *, login=None, email=None, name=None, message="работа", when=None):
    return {
        "sha": sha,
        "author": {"login": login} if login else None,
        "commit": {
            "message": message,
            "author": {
                "email": email,
                "name": name,
                "date": (when or NOW).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        },
    }


def sync(db, team, client):
    return asyncio.run(_sync_commits_and_reviews(db, team, client))


def test_sync_returns_a_complete_report(db, team):
    """Тот самый упавший ответ: все ключи на месте и ошибки нет."""
    member = make_member(db, team, name="anna")
    client = FakeGitHub(commits=[commit_payload("abc123", login="anna", message="правки")])

    result = sync(db, team, client)

    assert "error" not in result
    assert set(result) == {
        "new_commits",
        "linked_commits",
        "rematched_authors",
        "stats_fetched",
        "new_reviews",
        "unresolved_authors",
    }
    assert result["new_commits"] == 1
    assert db.query(Commit).filter(Commit.team_id == team.id).count() == 1
    assert db.query(Commit).first().member_id == member.id


def test_commit_of_an_unknown_author_stays_ownerless(db, team):
    make_member(db, team, name="anna")
    client = FakeGitHub(commits=[commit_payload("dead01", login="stranger")])

    result = sync(db, team, client)

    assert result["new_commits"] == 1
    assert result["unresolved_authors"] == ["stranger"]
    assert db.query(Commit).first().member_id is None


def test_author_is_picked_up_once_github_is_linked(db, team):
    """Человек привязал GitHub уже после того, как его коммиты синканулись.
    Следующий синк обязан их подобрать, иначе работа не засчитается вообще."""
    member = make_member(db, team, name="Поздний", with_github=False)
    sync(db, team, FakeGitHub(commits=[commit_payload("beef01", login="late-comer")]))
    assert db.query(Commit).first().member_id is None

    db.add(GithubMapping(member_id=member.id, github_username="late-comer"))
    db.commit()

    result = sync(db, team, FakeGitHub(commits=[]))

    assert result["rematched_authors"] == 1
    assert db.query(Commit).first().member_id == member.id


def test_sync_links_commits_to_tasks_by_number(db, team):
    member = make_member(db, team, name="anna")
    task = make_task(db, team, assignee=member, created_days_ago=5)
    client = FakeGitHub(commits=[commit_payload("f00d01", login="anna", message=f"починил #{task.number}")])

    result = sync(db, team, client)

    assert result["linked_commits"] == 1
    assert db.query(Commit).first().task_id == task.id


def test_known_commits_are_not_inserted_twice(db, team):
    make_member(db, team, name="anna")
    payload = [commit_payload("same01", login="anna")]

    assert sync(db, team, FakeGitHub(commits=payload))["new_commits"] == 1
    assert sync(db, team, FakeGitHub(commits=payload))["new_commits"] == 0
    assert db.query(Commit).count() == 1


def test_stats_are_fetched_for_new_commits(db, team):
    make_member(db, team, name="anna")

    result = sync(db, team, FakeGitHub(commits=[commit_payload("stat01", login="anna")]))

    assert result["stats_fetched"] == 1
    row = db.query(Commit).first()
    assert (row.additions, row.deletions, row.stats_fetched) == (10, 2, True)


def test_pr_reviews_are_recorded_once(db, team):
    make_member(db, team, name="anna")
    client = FakeGitHub(
        pulls=[{"number": 7}],
        reviews={7: [{"id": 555, "user": {"login": "anna"}, "submitted_at": "2026-03-14T10:00:00Z", "state": "COMMENTED"}]},
    )

    assert sync(db, team, client)["new_reviews"] == 1
    assert sync(db, team, client)["new_reviews"] == 0


def test_a_broken_pr_call_does_not_lose_the_commits(db, team):
    """Ревью — не повод терять уже собранные коммиты: GitHub может отвалиться
    на середине, и синк обязан отдать то, что успел."""

    class HalfBroken(FakeGitHub):
        async def list_recent_pull_requests(self, state="all", limit=30):
            raise RuntimeError("GitHub упал")

    make_member(db, team, name="anna")

    result = sync(db, team, HalfBroken(commits=[commit_payload("half01", login="anna")]))

    assert result["new_commits"] == 1
    assert result["new_reviews"] == 0
    assert db.query(Commit).count() == 1


def test_commits_of_another_team_are_not_touched(db, team):
    make_member(db, team, name="anna")
    other = make_team(db, name="Чужой проект")
    stranger = make_member(db, other, name="other-guy")
    from tests.conftest import make_commit

    make_commit(db, other, stranger, message="чужой коммит")

    sync(db, team, FakeGitHub(commits=[commit_payload("mine01", login="anna")]))

    assert db.query(Commit).filter(Commit.team_id == team.id).count() == 1
    assert db.query(Commit).filter(Commit.team_id == other.id).count() == 1
