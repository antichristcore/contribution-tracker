"""Чистые функции формулы вклада: normalize, penalty, contribution_score.

База не нужна — вход и выход детерминированы. Это тот слой, где ошибка
незаметна глазами, но красит живого человека в жёлтый.
"""

import pytest

from backend.app.services.scoring import (
    MAX_LINES_PER_COMMIT,
    NORMALIZE_CAP,
    PENALTY_MAX,
    RHYTHM_TARGET_DAYS,
    SCORE_MAX,
    W_CODE,
    W_REVIEWS,
    W_RHYTHM,
    W_TASKS,
    contribution_score,
    normalize,
    peer_median,
    penalty,
    score_breakdown,
)
from tests.conftest import raw_metrics


def median_member(**overrides):
    """Участник ровно на уровне команды: все задачи в срок, медианный объём
    кода, ровный ритм, медианное число ревью."""
    base = dict(
        commits_lines_changed_7d=100,
        active_days_14d=RHYTHM_TARGET_DAYS,
        tasks_assigned=4,
        tasks_deadline_eligible=4,
        tasks_completed_on_time=4,
        pr_review_comments_given=2,
    )
    base.update(overrides)
    return raw_metrics(**base)


PEERS_LINES = [100, 100]
PEERS_REVIEWS = [2, 2]


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


def test_peer_median_ignores_missing_values():
    assert peer_median([None, 10, 30]) == 20
    assert peer_median([]) == 0


# --- penalty -----------------------------------------------------------------


@pytest.mark.parametrize("stuck_days, expected", [(0, 0.0), (1, 1 / 7), (3, 3 / 7), (7, 1.0), (30, 1.0)])
def test_penalty_is_linear_and_capped_at_red_threshold(stuck_days, expected):
    assert penalty(stuck_days) == pytest.approx(expected)


# --- шкала -------------------------------------------------------------------


def test_score_is_none_without_data():
    """«Нет данных» — это не ноль. Молчаливый ноль читался бы как «ничего не делал»."""
    assert contribution_score(raw_metrics(has_data=False), [100], [2]) is None
    assert score_breakdown(raw_metrics(has_data=False), [100], [2]) is None


def test_median_member_lands_around_the_middle_of_the_scale():
    """Все задачи в срок, ровный ритм, медианный объём кода. Относительные
    компоненты дают на медиане половину веса, абсолютные — сколько сделал."""
    score = contribution_score(median_member(), PEERS_LINES, PEERS_REVIEWS)
    # 40 + 17.5 + 15 + 5 = 77.5, итог округляется до целого.
    assert score == round(W_TASKS + W_CODE / 2 + W_RHYTHM + W_REVIEWS / 2 + 0.001)


def test_doing_everything_at_double_the_median_reaches_the_top():
    raw = median_member(commits_lines_changed_7d=10_000, pr_review_comments_given=999)
    assert contribution_score(raw, PEERS_LINES, PEERS_REVIEWS) == SCORE_MAX


def test_doing_nothing_is_zero_not_negative():
    """Шкала не уходит в минус: «0 из 100» человек читает, «−12 из 100» — нет."""
    raw = raw_metrics(tasks_assigned=2, tasks_deadline_eligible=2, tasks_status_stuck_days_max=30)
    assert contribution_score(raw, PEERS_LINES, PEERS_REVIEWS) == 0


def test_score_never_leaves_the_scale():
    for stuck in (0, 3, 7, 90):
        for lines in (0, 100, 10_000):
            raw = median_member(commits_lines_changed_7d=lines, tasks_status_stuck_days_max=stuck)
            assert 0 <= contribution_score(raw, PEERS_LINES, PEERS_REVIEWS) <= SCORE_MAX


def test_stuck_task_costs_up_to_the_penalty_weight():
    clean = contribution_score(median_member(), PEERS_LINES, PEERS_REVIEWS)
    stuck = contribution_score(
        median_member(tasks_status_stuck_days_max=7), PEERS_LINES, PEERS_REVIEWS
    )
    assert clean - stuck == PENALTY_MAX


# --- доля задач --------------------------------------------------------------


@pytest.mark.parametrize("eligible, on_time, ratio", [(4, 4, 1.0), (4, 2, 0.5), (4, 0, 0.0), (1, 1, 1.0)])
def test_tasks_component_is_the_on_time_share(eligible, on_time, ratio):
    raw = median_member(tasks_deadline_eligible=eligible, tasks_completed_on_time=on_time)
    full = contribution_score(median_member(), PEERS_LINES, PEERS_REVIEWS)
    actual = contribution_score(raw, PEERS_LINES, PEERS_REVIEWS)
    assert full - actual == pytest.approx(W_TASKS * (1 - ratio), abs=1)


# --- ритм --------------------------------------------------------------------


@pytest.mark.parametrize(
    "days, share",
    [(0, 0.0), (1, 1 / RHYTHM_TARGET_DAYS), (RHYTHM_TARGET_DAYS, 1.0), (14, 1.0)],
)
def test_rhythm_counts_days_not_volume(days, share):
    """Ритм отличает ровную работу от аврала: важно, сколько дней человек
    появлялся, а не сколько строк он написал в один заход."""
    raw = median_member(active_days_14d=days)
    component = next(
        c for c in score_breakdown(raw, PEERS_LINES, PEERS_REVIEWS)["components"] if c["key"] == "rhythm"
    )
    assert component["value"] == pytest.approx(share)
    assert component["points"] == pytest.approx(W_RHYTHM * share, abs=0.05)


def test_max_lines_per_commit_is_configured_sanely():
    """Константа-предохранитель. Если её случайно поднимут до миллиона,
    защита от сгенерированных файлов перестанет работать молча."""
    assert 100 <= MAX_LINES_PER_COMMIT <= 5_000
