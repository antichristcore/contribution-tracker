"""Привязка коммитов к задачам по «#номер»: task_linking.

Это единственный мост между реальной работой в git и доской задач. Ложное
срабатывание тихо утаскивает коммит в чужую задачу, поэтому охранные условия
(та же команда, коммит не старше задачи) проверяются отдельно.

Ключевых слов («fixes», «closes», «готово») в разборе больше нет: люди пишут
«fix #42» в смысле «работаю над этим», и задача закрывалась на первом же
коммите. Закрыть задачу может только человек.
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
        ("Fix login bug #42", [42], "обычное упоминание"),
        ("fixes #42", [42], "fixes больше не особенное слово"),
        ("closes #7", [7], "closes тоже"),
        ("закрывает #3", [3], "русское ключевое слово ничего не меняет"),
        ("готово #5", [5], "и «готово» тоже"),
        ("refactor #10 and fixes #11", [10, 11], "две ссылки"),
        ("порядок сохраняется: #9 #8", [9, 8], "порядок как в тексте"),
        ("нет ссылок вообще", [], "пустой результат"),
        ("", [], "пустая строка"),
        (None, [], "сообщения нет"),
        ("bump to v1.2 #3", [3], "версия рядом ничему не мешает"),
    ],
)
def test_parse_task_references(message, expected, case):
    assert parse_task_references(message) == expected, case


# --- привязка к реальной задаче ---------------------------------------------


def test_links_commit_to_task_of_the_same_team(db, team):
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=10)

    linked = link_commit_to_task(db, team.id, f"работа над задачей #{task.id}", NOW)

    assert linked is not None
    assert linked.id == task.id


def test_closing_keyword_is_just_a_link_now(db, team):
    """Регрессия: «fix #42» закрывал задачу, хотя человек имел в виду
    «я над этим работаю». Ссылка привязывает и только."""
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=10, status=TaskStatus.todo)

    linked = link_commit_to_task(db, team.id, f"fixes #{task.id}", NOW)

    assert linked is not None
    assert linked.status is TaskStatus.todo


def test_task_of_another_team_is_never_linked(db, team):
    """id задач сквозные по всей базе — без проверки команды коммит одной
    команды закрыл бы задачу другой."""
    other = make_team(db, name="Чужая команда")
    stranger = make_member(db, other, name="Stranger")
    foreign_task = make_task(db, other, assignee=stranger, created_days_ago=10)

    assert link_commit_to_task(db, team.id, f"по задаче #{foreign_task.id}", NOW) is None


def test_commit_older_than_the_task_is_not_linked(db, team):
    """Коммит, написанный до появления задачи, не может быть работой по ней.

    Этот же guard гасит ложные срабатывания на номерах issue из старой истории
    репозитория, которые случайно совпали с id задачи.
    """
    member = make_member(db, team)
    task = make_task(db, team, assignee=member, created_days_ago=3)
    long_before = NOW - timedelta(days=30)

    assert link_commit_to_task(db, team.id, f"по задаче #{task.id}", long_before) is None


def test_unknown_task_id_is_ignored(db, team):
    assert link_commit_to_task(db, team.id, "по задаче #999999", NOW) is None


def test_first_valid_reference_wins(db, team):
    """В сообщении две ссылки: берётся первая подходящая, а не последняя."""
    member = make_member(db, team)
    first = make_task(db, team, assignee=member, title="Первая", created_days_ago=10)
    second = make_task(db, team, assignee=member, title="Вторая", created_days_ago=10)

    linked = link_commit_to_task(db, team.id, f"#{first.id} и #{second.id}", NOW)

    assert linked is not None
    assert linked.id == first.id


def test_foreign_reference_does_not_block_a_valid_one(db, team):
    """Ссылка на чужую задачу пропускается, а не обрывает разбор."""
    other = make_team(db, name="Чужая команда")
    stranger = make_member(db, other, name="Stranger")
    foreign = make_task(db, other, assignee=stranger, created_days_ago=10)

    member = make_member(db, team)
    mine = make_task(db, team, assignee=member, created_days_ago=10)

    linked = link_commit_to_task(db, team.id, f"по #{foreign.id}, related #{mine.id}", NOW)

    assert linked is not None
    assert linked.id == mine.id


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

    linked = link_commit_to_task(db, team.id, f"доработка #{task.id}", NOW)

    assert linked is not None
    assert linked.id == task.id
