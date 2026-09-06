"""Сбор сырых метрик из базы: get_raw_metrics.

Здесь проверяется то, что нельзя увидеть в формуле — какие строки базы вообще
попадают в окно, а какие отсекаются.
"""

import pytest

from backend.app.models import TaskStatus
from backend.app.services.scoring import MAX_LINES_PER_COMMIT, get_raw_metrics
from tests.conftest import (
    NOW,
    make_commit,
    make_member,
    make_pr_review,
    make_status_change,
    make_task,
)

# --- строки кода -------------------------------------------------------------


def test_huge_commit_is_clamped(db, team):
    """Сгенерированный файл на 10 000 строк не должен делать автора героем."""
    member = make_member(db, team)
    make_commit(db, team, member, days_ago=1, additions=9_000, deletions=1_000)

    raw = get_raw_metrics(db, member, NOW)

    assert raw["commits_lines_changed_7d"] == MAX_LINES_PER_COMMIT
    assert raw["commits_count_7d"] == 1


def test_clamp_applies_per_commit_not_per_week(db, team):
    """Обрезается каждый коммит по отдельности — честный автор с тремя
    крупными коммитами не должен упираться в тот же потолок, что и один дамп."""
    member = make_member(db, team)
    for _ in range(3):
        make_commit(db, team, member, days_ago=1, additions=5_000, deletions=0)

    raw = get_raw_metrics(db, member, NOW)

    assert raw["commits_lines_changed_7d"] == 3 * MAX_LINES_PER_COMMIT


def test_normal_commits_are_summed_untouched(db, team):
    member = make_member(db, team)
    make_commit(db, team, member, days_ago=1, additions=200, deletions=50)
    make_commit(db, team, member, days_ago=3, additions=300, deletions=0)

    assert get_raw_metrics(db, member, NOW)["commits_lines_changed_7d"] == 550


def test_commit_without_stats_counts_as_zero_lines(db, team):
    """stats у коммита могут быть ещё не догружены (stats_fetched=false) —
    это не должно ронять расчёт."""
    member = make_member(db, team)
    make_commit(db, team, member, days_ago=1, additions=None, deletions=None)

    raw = get_raw_metrics(db, member, NOW)

    assert raw["commits_count_7d"] == 1
    assert raw["commits_lines_changed_7d"] == 0


# --- окно в 7 дней -----------------------------------------------------------


@pytest.mark.parametrize(
    "days_ago, expected_count",
    [
        (0, 1),
        (6, 1),
        (7, 1),  # граница включительно
        (8, 0),
        (30, 0),
    ],
)
def test_seven_day_window_boundaries(db, team, days_ago, expected_count):
    member = make_member(db, team)
    make_commit(db, team, member, days_ago=days_ago)

    assert get_raw_metrics(db, member, NOW)["commits_count_7d"] == expected_count


def test_reviews_outside_window_are_excluded(db, team):
    member = make_member(db, team)
    make_pr_review(db, team, member, days_ago=2)
    make_pr_review(db, team, member, days_ago=20, pr_number=2)

    assert get_raw_metrics(db, member, NOW)["pr_review_comments_given"] == 1


# --- задачи ------------------------------------------------------------------


def test_task_done_before_deadline_counts_as_on_time(db, team):
    member = make_member(db, team)
    make_task(
        db,
        team,
        assignee=member,
        status=TaskStatus.done,
        completed_days_ago=5,
        deadline_days_ago=3,
    )

    raw = get_raw_metrics(db, member, NOW)

    assert raw["tasks_assigned"] == 1
    assert raw["tasks_completed_on_time"] == 1


def test_task_done_after_deadline_does_not_count(db, team):
    member = make_member(db, team)
    make_task(
        db,
        team,
        assignee=member,
        status=TaskStatus.done,
        completed_days_ago=1,
        deadline_days_ago=3,
    )

    assert get_raw_metrics(db, member, NOW)["tasks_completed_on_time"] == 0


def test_task_without_deadline_never_counts_as_on_time(db, team):
    """Открытый вопрос для аналитика: задача сделана, но дедлайн не проставлен —
    участник не получает за неё ничего. Тест фиксирует текущее поведение."""
    member = make_member(db, team)
    make_task(db, team, assignee=member, status=TaskStatus.done, completed_days_ago=2)

    raw = get_raw_metrics(db, member, NOW)

    assert raw["tasks_assigned"] == 1
    assert raw["tasks_completed_on_time"] == 0


def test_stuck_days_take_the_worst_open_task(db, team):
    member = make_member(db, team)
    make_task(db, team, assignee=member, status=TaskStatus.in_progress, status_changed_days_ago=2)
    make_task(db, team, assignee=member, status=TaskStatus.todo, status_changed_days_ago=9)

    assert get_raw_metrics(db, member, NOW)["tasks_status_stuck_days_max"] == 9


def test_closed_tasks_do_not_count_as_stuck(db, team):
    """Задача, закрытая месяц назад, не должна вечно держать участника красным."""
    member = make_member(db, team)
    make_task(
        db,
        team,
        assignee=member,
        status=TaskStatus.done,
        status_changed_days_ago=40,
        completed_days_ago=40,
        deadline_days_ago=40,
    )

    assert get_raw_metrics(db, member, NOW)["tasks_status_stuck_days_max"] == 0


# --- последняя активность и «нет данных» -------------------------------------


def test_last_activity_takes_the_most_recent_signal(db, team):
    """Активность — это не только коммиты: сдвиг задачи и ревью тоже считаются."""
    member = make_member(db, team)
    make_commit(db, team, member, days_ago=6)
    make_pr_review(db, team, member, days_ago=2)
    task = make_task(db, team, assignee=member)
    make_status_change(db, task, member, days_ago=4)

    assert get_raw_metrics(db, member, NOW)["last_activity_days_ago"] == 2


def test_last_activity_is_none_when_nothing_happened(db, team):
    member = make_member(db, team)

    assert get_raw_metrics(db, member, NOW)["last_activity_days_ago"] is None


def test_member_without_github_and_tasks_has_no_data(db, team):
    """Честное «нет данных» вместо молчаливого нуля — заявленный принцип продукта."""
    member = make_member(db, team, with_github=False)

    assert get_raw_metrics(db, member, NOW)["has_data"] is False


def test_task_alone_is_enough_to_have_data(db, team):
    """Дизайнер без GitHub, но с задачами — это данные, а не пустота."""
    member = make_member(db, team, name="Дизайнер", role="design", with_github=False)
    make_task(db, team, assignee=member)

    assert get_raw_metrics(db, member, NOW)["has_data"] is True


def test_other_members_activity_does_not_leak(db, team):
    """Метрики считаются по конкретному участнику, а не по всей команде."""
    alice = make_member(db, team, name="Alice")
    bob = make_member(db, team, name="Bob")
    make_commit(db, team, bob, days_ago=1, additions=500, deletions=0)

    raw = get_raw_metrics(db, alice, NOW)

    assert raw["commits_count_7d"] == 0
    assert raw["commits_lines_changed_7d"] == 0
