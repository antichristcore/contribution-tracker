"""Чистые функции формулы вклада: normalize, penalty, contribution_score.

База не нужна — вход и выход детерминированы. Это тот слой, где ошибка
незаметна глазами, но красит живого человека в жёлтый.
"""

import pytest

from backend.app.services.scoring import (
    MAX_LINES_PER_COMMIT,
    NORMALIZE_CAP,
    W_LINES,
    W_PENALTY,
    W_REVIEWS,
    W_TASKS,
    contribution_score,
    normalize,
    penalty,
)
from tests.conftest import raw_metrics

# --- normalize ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, peers, expected, case",
    [
        (100, [100, 100, 100], 1.0, "ровно медиана -> 1.0"),
        (50, [100, 100], 0.5, "половина медианы"),
        (150, [100, 100], 1.5, "полторы медианы"),
        (199, [100, 100], 1.99, "чуть ниже потолка не режется"),
        (200, [100, 100], NORMALIZE_CAP, "ровно на потолке"),
        (10_000, [100, 100], NORMALIZE_CAP, "аномалия срезается потолком"),
        (5, [], 1.0, "не с кем сравнивать, но активность есть"),
        (0, [], 0.0, "не с кем сравнивать и активности нет"),
        (7, [0, 0, 0], 1.0, "мёртвая команда: любой ненулевой вклад = 1.0"),
        (3, [None, 100, 100], 0.03, "None среди соседей игнорируется"),
    ],
)
def test_normalize(value, peers, expected, case):
    assert normalize(value, peers) == pytest.approx(expected), case


def test_normalize_never_exceeds_cap():
    """Главная защита от «залил сгенерированный файл — стал лучшим в команде».

    Без потолка один участник улетал в norm=20 и утягивал медиану так, что
    нормальные люди начинали проходить правило «на 40% ниже медианы».
    """
    for value in (500, 5_000, 50_000, 500_000):
        assert normalize(value, [100, 100]) <= NORMALIZE_CAP


# --- penalty -----------------------------------------------------------------


@pytest.mark.parametrize(
    "stuck_days, expected",
    [
        (0, 0.0),
        (1, 1 / 7),
        (3, 3 / 7),
        (7, 1.0),
        (30, 1.0),
    ],
)
def test_penalty_is_linear_and_capped_at_red_threshold(stuck_days, expected):
    assert penalty(stuck_days) == pytest.approx(expected)


# --- contribution_score ------------------------------------------------------


def test_score_is_none_without_data():
    """«Нет данных» — это не ноль. Молчаливый ноль читался бы как «ничего не делал»."""
    assert contribution_score(raw_metrics(has_data=False), [100], [2]) is None


def test_score_of_fully_median_member():
    raw = raw_metrics(
        commits_lines_changed_7d=100,
        tasks_assigned=4,
        tasks_completed_on_time=4,
        pr_review_comments_given=2,
    )
    # 0.35*1 + 0.35*1 + 0.15*1 - 0 = 0.85
    assert contribution_score(raw, [100, 100], [2, 2]) == pytest.approx(0.85)


def test_stuck_task_costs_exactly_the_penalty_weight():
    kwargs = dict(
        commits_lines_changed_7d=100,
        tasks_assigned=4,
        tasks_completed_on_time=4,
        pr_review_comments_given=2,
    )
    clean = contribution_score(raw_metrics(**kwargs), [100, 100], [2, 2])
    stuck = contribution_score(
        raw_metrics(**kwargs, tasks_status_stuck_days_max=7), [100, 100], [2, 2]
    )
    assert clean - stuck == pytest.approx(W_PENALTY)


def test_member_without_tasks_is_not_punished_for_it():
    """Задач не назначено — это решение тимлида, а не поведение участника.

    Раньше компонента считалась нулём и человек, которому просто ещё ничего
    не дали, терял 35% score. Сейчас вес перераспределяется.
    """
    no_tasks = contribution_score(
        raw_metrics(commits_lines_changed_7d=100, pr_review_comments_given=2, tasks_assigned=0),
        [100, 100],
        [2, 2],
    )
    all_on_time = contribution_score(
        raw_metrics(
            commits_lines_changed_7d=100,
            pr_review_comments_given=2,
            tasks_assigned=4,
            tasks_completed_on_time=4,
        ),
        [100, 100],
        [2, 2],
    )
    assert no_tasks == pytest.approx(all_on_time)


def test_weights_still_sum_to_the_documented_total():
    """Перераспределение веса не должно менять сумму весов из PROJECT.md."""
    assert W_LINES + W_TASKS + W_REVIEWS == pytest.approx(0.85)
    scale = (W_LINES + W_TASKS + W_REVIEWS) / (W_LINES + W_REVIEWS)
    assert W_LINES * scale + W_REVIEWS * scale == pytest.approx(W_LINES + W_TASKS + W_REVIEWS)


def test_half_done_tasks_give_half_the_task_component():
    kwargs = dict(commits_lines_changed_7d=100, pr_review_comments_given=2)
    full = contribution_score(
        raw_metrics(**kwargs, tasks_assigned=4, tasks_completed_on_time=4), [100, 100], [2, 2]
    )
    half = contribution_score(
        raw_metrics(**kwargs, tasks_assigned=4, tasks_completed_on_time=2), [100, 100], [2, 2]
    )
    assert full - half == pytest.approx(W_TASKS * 0.5)


@pytest.mark.parametrize("tasks_assigned", [0, 4])
def test_score_stays_inside_known_bounds(tasks_assigned):
    """Верхняя граница score конечна — иначе шкала на дашборде необъяснима.

    С задачами потолок 1.35 (0.35*2 + 0.35 + 0.15*2), без задач — 1.70,
    потому что вес перераспределяется на две компоненты, у каждой потолок 2.0.
    Разница осознанная, но её стоит помнить, читая дашборд.
    """
    raw = raw_metrics(
        commits_lines_changed_7d=10_000,
        pr_review_comments_given=999,
        tasks_assigned=tasks_assigned,
        tasks_completed_on_time=tasks_assigned,
    )
    score = contribution_score(raw, [100, 100], [2, 2])
    expected_cap = 1.35 if tasks_assigned else 1.70
    assert score == pytest.approx(expected_cap)
    assert score >= -W_PENALTY


def test_max_lines_per_commit_is_configured_sanely():
    """Константа-предохранитель. Если её случайно поднимут до миллиона,
    защита от сгенерированных файлов перестанет работать молча."""
    assert 100 <= MAX_LINES_PER_COMMIT <= 5_000
