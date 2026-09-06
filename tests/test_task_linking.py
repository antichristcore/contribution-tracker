"""Привязка коммитов к задачам по «#id»: task_linking.

Это единственный мост между реальной работой в git и доской задач. Ложное
срабатывание здесь тихо закрывает чужую задачу, поэтому охранные условия
(та же команда, коммит не старше задачи) проверяются отдельно.
"""

from datetime import timedelta

import pytest

from backend.app.models import TaskStatus
from backend.app.services.task_linking import link_commit_to_task, parse_task_references
from tests.conftest import NOW, make_member, make_task, make_team

# --- разбор сообщения --------------------------------------------------------


@pytest.mark.parametrize(
    "message, expected, case",
    [
        ("Fix login bug #42", [(42, False)], "упоминание без ключевого слова не закрывает"),
        ("fixes #42", [(42, True)], "fixes закрывает"),
        ("Fixed #42", [(42, True)], "регистр не важен"),
        ("closes #7", [(7, True)], "closes"),
        ("closed #7", [(7, True)], "closed"),
        ("close #7", [(7, True)], "close"),
        ("resolve #12", [(12, True)], "resolve"),
        ("resolved #12", [(12, True)], "resolved"),
        ("закрывает #3", [(3, True)], "русское ключевое слово"),
        ("готово #5", [(5, True)], "русское «готово»"),
        ("refactor #10 and fixes #11", [(10, False), (11, True)], "две ссылки, разный статус"),
        ("порядок сохраняется: #9 #8", [(9, False), (8, False)], "порядок как в тексте"),
        ("нет ссылок вообще", [], "пустой результат"),
        ("", [], "пустая строка"),
        (None, [], "сообщения нет"),
        ("bump to v1.2 #3", [(3, False)], "версия рядом не считается закрытием"),
    ],
)
def test_parse_task_references(message, expected, case):
    assert parse_task_references(message) == expected, case


def test_keyword_must_stand_immediately_before_the_reference():
    """«fix» в середине текста не должен закрывать задачу, упомянутую позже, —
    иначе обычное «hotfix для рефакторинга, см. #12» закроет чужую задачу."""
    assert parse_task_references("fix того, что сломалось вчера, см. #12") == [(12, False)]


# --- привязка к реальной задаче ---------------------------------------------


def test_links_commit_to_task_of_the_same_team(db, team):
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=10)

    result = link_commit_to_task(db, team.id, f"работа над задачей #{task.id}", NOW)

    assert result is not None
    linked, is_closing = result
    assert linked.id == task.id
    assert is_closing is False


def test_closing_keyword_is_reported(db, team):
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=10)

    result = link_commit_to_task(db, team.id, f"fixes #{task.id}", NOW)

    assert result is not None
    assert result[1] is True


def test_task_of_another_team_is_never_linked(db, team):
    """id задач сквозные по всей базе — без проверки команды коммит одной
    команды закрыл бы задачу другой."""
    other = make_team(db, name="Чужая команда")
    stranger = make_member(db, other, name="Stranger")
    foreign_task = make_task(db, other, assignee=stranger, created_days_ago=10)

    assert link_commit_to_task(db, team.id, f"fixes #{foreign_task.id}", NOW) is None


def test_commit_older_than_the_task_is_not_linked(db, team):
    """Коммит, написанный до появления задачи, не может быть работой по ней.

    Этот же guard гасит ложные срабатывания на номерах issue из старой истории
    репозитория, которые случайно совпали с id задачи.
    """
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=3)
    long_before = NOW - timedelta(days=30)

    assert link_commit_to_task(db, team.id, f"fixes #{task.id}", long_before) is None


def test_unknown_task_id_is_ignored(db, team):
    assert link_commit_to_task(db, team.id, "fixes #999999", NOW) is None


def test_first_valid_reference_wins(db, team):
    """В сообщении две ссылки: берётся первая подходящая, а не последняя."""
    member = make_member(db, team)
    first = make_task(db, team, assignee=member, title="Первая", created_days_ago=10)
    second = make_task(db, team, assignee=member, title="Вторая", created_days_ago=10)

    result = link_commit_to_task(db, team.id, f"#{first.id} и #{second.id}", NOW)

    assert result is not None
    assert result[0].id == first.id


def test_foreign_reference_does_not_block_a_valid_one(db, team):
    """Ссылка на чужую задачу пропускается, а не обрывает разбор."""
    other = make_team(db, name="Чужая команда")
    stranger = make_member(db, other, name="Stranger")
    foreign = make_task(db, other, assignee=stranger, created_days_ago=10)

    member = make_member(db, team)
    mine = make_task(db, team, assignee=member, created_days_ago=10)

    result = link_commit_to_task(db, team.id, f"fixes #{foreign.id}, related #{mine.id}", NOW)

    assert result is not None
    assert result[0].id == mine.id


def test_done_task_can_still_be_referenced(db, team):
    """Коммит по уже закрытой задаче должен привязываться — иначе доработки
    после закрытия теряются и вклад участника недосчитывается."""
    member = make_member(db, team)
    task = make_task(
        db,
        team,
        assignee=member,
        status=TaskStatus.done,
        created_days_ago=10,
        completed_days_ago=2,
        deadline_days_ago=1,
    )

    result = link_commit_to_task(db, team.id, f"доработка #{task.id}", NOW)

    assert result is not None
    assert result[0].id == task.id
