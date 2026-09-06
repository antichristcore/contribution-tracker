"""Тест-матрица по формуле вклада.

Покрывает четыре дефекта, найденных при ревью:
  1. normalize() без потолка — аномальный коммит ломал шкалу;
  2. tasks_assigned = 0 отнимал 35% у человека, которому не дали задач;
  3. нормализация «по роли» молча откатывалась на всю команду;
  4. отсутствие потолка на размер одного коммита.
"""

import pytest
from tests.conftest import NOW, make_commit, make_member, make_task, raw_metrics

from backend.app.models import TaskStatus
from backend.app.services.scoring import (
    MAX_LINES_PER_COMMIT,
    NORMALIZE_CAP,
    STUCK_RED_DAYS,
    W_LINES,
    W_PENALTY,
    W_REVIEWS,
    W_TASKS,
    compute_team_scores,
    contribution_score,
    get_raw_metrics,
    normalize,
    penalty,
)

# Во сколько раз растут веса оставшихся компонент, когда задач не назначено.
ZERO_TASK_SCALE = (W_LINES + W_TASKS + W_REVIEWS) / (W_LINES + W_REVIEWS)


# --- normalize ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, peers, expected",
    [
        (100, [100, 100, 100], 1.0),   # ровно медиана
        (50, [100, 100, 100], 0.5),    # вдвое ниже
        (200, [100, 100, 100], 2.0),   # ровно на потолке
        (0, [100, 100], 0.0),          # ничего не сделал
        (5, [0, 0, 0], 1.0),           # медиана 0, но активность есть
        (0, [0, 0, 0], 0.0),           # медиана 0 и активности нет
        (100, [], 1.0),                # не с кем сравнивать
    ],
)
def test_normalize_basic(value, peers, expected):
    assert normalize(value, peers) == pytest.approx(expected)


def test_normalize_capped_on_outlier():
    """Дефект №1: 10 000 строк против медианы 500 давали норму 20."""
    assert normalize(10_000, [500, 500, 500]) == NORMALIZE_CAP


def test_outlier_cannot_dominate_the_scale():
    """Даже с аномалией вклад по коду не превышает своего веса × потолок."""
    score = contribution_score(
        raw_metrics(commits_lines_changed_7d=10_000, tasks_assigned=1, tasks_completed_on_time=1),
        peers_lines_changed=[500, 500, 500],
        peers_pr_reviews=[0, 0],
    )
    assert score == pytest.approx(W_LINES * NORMALIZE_CAP + W_TASKS * 1.0)
    assert score <= W_LINES * NORMALIZE_CAP + W_TASKS + W_REVIEWS * NORMALIZE_CAP


# --- потолок на один коммит ---------------------------------------------------


def test_generated_file_commit_is_capped(db, team):
    """Дефект №4: package-lock.json на 10 000 строк засчитывается как потолок."""
    m = make_member(db, team, name="Аня")
    make_commit(db, team, m, days_ago=1, additions=9_500, deletions=500)

    assert get_raw_metrics(db, m, NOW)["commits_lines_changed_7d"] == MAX_LINES_PER_COMMIT


def test_many_normal_commits_are_not_capped(db, team):
    """Потолок на коммит, а не на неделю: 5 обычных коммитов складываются целиком."""
    m = make_member(db, team, name="Боря")
    for _ in range(5):
        make_commit(db, team, m, days_ago=1, additions=100, deletions=20)

    assert get_raw_metrics(db, m, NOW)["commits_lines_changed_7d"] == 5 * 120


def test_commits_outside_the_window_are_ignored(db, team):
    m = make_member(db, team, name="Вера")
    make_commit(db, team, m, days_ago=1, additions=100, deletions=0)
    make_commit(db, team, m, days_ago=30, additions=999, deletions=0)

    assert get_raw_metrics(db, m, NOW)["commits_lines_changed_7d"] == 100


# --- компонента задач ---------------------------------------------------------


def test_no_tasks_assigned_is_neutral_not_zero():
    """Дефект №2: новичок без задач не должен терять 35%.

    Оба участника коммитят ровно на уровне медианы. Разница между ними только
    в том, что одному тимлид успел назначить задачу, а другому нет.
    """
    peers = [100, 100]
    newcomer = raw_metrics(commits_lines_changed_7d=100, tasks_assigned=0)
    with_task = raw_metrics(commits_lines_changed_7d=100, tasks_assigned=1, tasks_completed_on_time=1)

    score_newcomer = contribution_score(newcomer, peers, [0, 0])
    score_with_task = contribution_score(with_task, peers, [0, 0])

    assert score_newcomer == pytest.approx(W_LINES * ZERO_TASK_SCALE)
    # До фикса разрыв был ровно W_TASKS = 0.35 — новичок проваливался в жёлтый
    # ни за что. Теперь отставание втрое меньше.
    assert score_with_task - score_newcomer < W_TASKS / 3


def test_zero_tasks_redistributes_weight_and_keeps_total():
    """Сумма весов не меняется: компонента задач исключается, остальные растут."""
    metrics = raw_metrics(commits_lines_changed_7d=100, pr_review_comments_given=1, tasks_assigned=0)

    # lines_norm = 1.0 и pr_norm = 1.0 -> идеально средний участник получает
    # всю положительную часть шкалы.
    assert contribution_score(metrics, [100, 100], [1, 1]) == pytest.approx(
        W_LINES + W_TASKS + W_REVIEWS
    )


def test_assigned_but_nothing_done_is_penalised():
    """Обратная сторона: задачи есть и не сделаны — это уже сигнал."""
    metrics = raw_metrics(commits_lines_changed_7d=100, tasks_assigned=4, tasks_completed_on_time=0)
    assert contribution_score(metrics, [100, 100], [0, 0]) == pytest.approx(W_LINES)


@pytest.mark.parametrize(
    "assigned, on_time, expected_ratio",
    [(4, 4, 1.0), (4, 2, 0.5), (4, 0, 0.0), (1, 1, 1.0)],
)
def test_tasks_ratio(assigned, on_time, expected_ratio):
    metrics = raw_metrics(tasks_assigned=assigned, tasks_completed_on_time=on_time)
    assert contribution_score(metrics, [0], [0]) == pytest.approx(W_TASKS * expected_ratio)


def test_only_tasks_finished_before_the_deadline_count(db, team):
    m = make_member(db, team, name="Гриша")
    # deadline_days_ago отрицательный -> дедлайн в будущем.
    make_task(db, team, m, status=TaskStatus.done, deadline_days_ago=-2, completed_days_ago=1)
    make_task(db, team, m, status=TaskStatus.done, deadline_days_ago=5, completed_days_ago=1)

    metrics = get_raw_metrics(db, m, NOW)
    assert metrics["tasks_assigned"] == 2
    assert metrics["tasks_completed_on_time"] == 1


# --- штраф за застой ----------------------------------------------------------


@pytest.mark.parametrize(
    "stuck_days, expected",
    [
        (0, 0.0),
        (1, 1 / STUCK_RED_DAYS),
        (STUCK_RED_DAYS - 1, (STUCK_RED_DAYS - 1) / STUCK_RED_DAYS),
        (STUCK_RED_DAYS, 1.0),
        (STUCK_RED_DAYS * 3, 1.0),  # дальше не растёт
    ],
)
def test_penalty_is_capped_at_the_red_threshold(stuck_days, expected):
    assert penalty(stuck_days) == pytest.approx(expected)


def test_penalty_lowers_the_score():
    metrics = raw_metrics(
        tasks_assigned=1, tasks_completed_on_time=1, tasks_status_stuck_days_max=STUCK_RED_DAYS
    )
    assert contribution_score(metrics, [0], [0]) == pytest.approx(W_TASKS - W_PENALTY)


# --- нет данных ---------------------------------------------------------------


def test_member_without_data_gets_none_not_zero():
    """«Нет данных» и «ноль» — разные вещи."""
    assert contribution_score(raw_metrics(has_data=False), [100], [1]) is None


def test_has_data_requires_github_or_tasks(db, team):
    m = make_member(db, team, name="Без гита", with_github=False)
    assert get_raw_metrics(db, m, NOW)["has_data"] is False

    make_task(db, team, m)
    assert get_raw_metrics(db, m, NOW)["has_data"] is True


# --- нормализация по роли -----------------------------------------------------


def test_peer_basis_is_team_when_role_has_one_person(db, team):
    """Дефект №3: в роли один человек — сравнение идёт по команде, и это видно."""
    backend = make_member(db, team, name="Аня", role="backend")
    frontend = make_member(db, team, name="Боря", role="frontend")
    for m in (backend, frontend):
        make_commit(db, team, m, additions=100)

    results = {r["member"].id: r for r in compute_team_scores(db, [backend, frontend], NOW)}

    assert results[backend.id]["peer_basis"] == "team"
    assert results[backend.id]["role_peer_count"] == 1


def test_peer_basis_is_role_when_there_are_enough_peers(db, team):
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    c = make_member(db, team, name="Вера", role="design")
    for m in (a, b, c):
        make_commit(db, team, m, additions=100)

    results = {r["member"].id: r for r in compute_team_scores(db, [a, b, c], NOW)}

    assert results[a.id]["peer_basis"] == "role"
    assert results[a.id]["role_peer_count"] == 2
    assert results[c.id]["peer_basis"] == "team"


def test_role_normalisation_protects_a_designer_from_backend_volume(db, team):
    """Смысл нормализации по роли: дизайнеров сравнивают с дизайнерами."""
    be1 = make_member(db, team, name="Бэк1", role="backend")
    be2 = make_member(db, team, name="Бэк2", role="backend")
    d1 = make_member(db, team, name="Диз1", role="design")
    d2 = make_member(db, team, name="Диз2", role="design")
    for m in (be1, be2):
        make_commit(db, team, m, additions=800, deletions=0)
    for m in (d1, d2):
        make_commit(db, team, m, additions=40, deletions=0)

    results = {r["member"].id: r for r in compute_team_scores(db, [be1, be2, d1, d2], NOW)}

    # Дизайнер пишет в 20 раз меньше строк, но внутри своей роли он ровно
    # средний — score не должен его за это наказывать.
    assert results[d1.id]["peer_basis"] == "role"
    assert results[d1.id]["score"] == pytest.approx(results[be1.id]["score"])


def test_members_without_data_do_not_drag_the_median(db, team):
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    ghost = make_member(db, team, name="Призрак", role="backend", with_github=False)
    for m in (a, b):
        make_commit(db, team, m, additions=100)

    results = {r["member"].id: r for r in compute_team_scores(db, [a, b, ghost], NOW)}

    assert results[ghost.id]["score"] is None
    assert results[a.id]["role_peer_count"] == 2  # призрак не считается сравнимым
    assert results[a.id]["score"] == pytest.approx(results[b.id]["score"])
