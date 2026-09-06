"""Формула вклада на живых данных: от строк в базе до балла.

Здесь же зафиксированы поломки, ради которых формулу переписывали. Обе были
найдены не в тестах, а на реальном проекте, где балл участника сводился к
`0.35 × (мои строки / медиана)`, а остальные 50% веса были структурно нулевыми:

  1. компонента ревью обнулялась в команде, которая коммитит прямо в main
     без PR, — минус 15% одинаково у всех;
  2. дедлайн стоял на полночь, и задача, сданная в день дедлайна днём,
     считалась просроченной, — минус ещё 35%.
"""

import pytest

from backend.app.models import TaskStatus
from backend.app.services.scoring import (
    MAX_LINES_PER_COMMIT,
    RHYTHM_WINDOW_DAYS,
    SCORE_MAX,
    W_REVIEWS,
    active_days,
    compute_team_scores,
    get_raw_metrics,
    team_has_reviews,
)
from tests.conftest import NOW, make_commit, make_member, make_pr_review, make_task

# --- потолок на один коммит ---------------------------------------------------


def test_generated_file_commit_is_capped(db, team):
    """package-lock.json на 10 000 строк засчитывается как потолок."""
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


# --- задачи и дедлайны --------------------------------------------------------


def test_task_closed_on_the_deadline_day_counts_as_on_time(db, team):
    """Регрессия. Дедлайн почти всегда стоит на полночь, и задача, сданная в
    тот же день в 11 утра, формально оказывалась просроченной. Срок считается
    по дню."""
    m = make_member(db, team, name="Гриша")
    task = make_task(db, team, m, status=TaskStatus.done, deadline_days_ago=1, completed_days_ago=1)
    # дедлайн — полночь того же дня, работа закончена днём
    task.deadline_at = task.deadline_at.replace(hour=0, minute=0)
    task.completed_at = task.completed_at.replace(hour=11, minute=11)
    db.commit()

    raw = get_raw_metrics(db, m, NOW)
    assert raw["tasks_deadline_eligible"] == 1
    assert raw["tasks_completed_on_time"] == 1


def test_task_closed_the_next_day_is_late(db, team):
    m = make_member(db, team, name="Дима")
    make_task(db, team, m, status=TaskStatus.done, deadline_days_ago=3, completed_days_ago=1)

    assert get_raw_metrics(db, m, NOW)["tasks_completed_on_time"] == 0


def test_task_without_a_deadline_is_out_of_the_ratio(db, team):
    """Дедлайн не проставил тимлид — исполнителю за это ничего не должно быть
    ни в плюс, ни в минус: задача не попадает ни в числитель, ни в знаменатель."""
    m = make_member(db, team, name="Женя")
    make_task(db, team, m, status=TaskStatus.done, completed_days_ago=2)

    raw = get_raw_metrics(db, m, NOW)
    assert raw["tasks_assigned"] == 1
    assert raw["tasks_deadline_eligible"] == 0


def test_open_task_with_a_future_deadline_is_not_a_failure_yet(db, team):
    """Срок ещё не наступил — это не провал и не успех, просто работа в процессе."""
    m = make_member(db, team, name="Зина")
    make_task(db, team, m, status=TaskStatus.in_progress, deadline_days_ago=-5)

    assert get_raw_metrics(db, m, NOW)["tasks_deadline_eligible"] == 0


def test_overdue_open_task_counts_against_the_ratio(db, team):
    """А просроченная и незакрытая — попадает в знаменатель, иначе метрику
    можно обойти, просто никогда ничего не завершая."""
    m = make_member(db, team, name="Игорь")
    make_task(db, team, m, status=TaskStatus.in_progress, deadline_days_ago=3)

    raw = get_raw_metrics(db, m, NOW)
    assert raw["tasks_deadline_eligible"] == 1
    assert raw["tasks_completed_on_time"] == 0


# --- ритм ---------------------------------------------------------------------


def test_active_days_counts_distinct_days(db, team):
    """Три коммита в один день — это один день активности, а не три."""
    m = make_member(db, team, name="Костя")
    for _ in range(3):
        make_commit(db, team, m, days_ago=2)
    make_commit(db, team, m, days_ago=5)

    assert active_days(db, m.id, NOW, RHYTHM_WINDOW_DAYS) == 2


def test_active_days_ignores_commits_outside_the_window(db, team):
    m = make_member(db, team, name="Лена")
    make_commit(db, team, m, days_ago=1)
    make_commit(db, team, m, days_ago=RHYTHM_WINDOW_DAYS + 5)

    assert active_days(db, m.id, NOW, RHYTHM_WINDOW_DAYS) == 1


def test_burst_of_work_scores_lower_than_the_same_work_spread_out(db, team):
    """Смысл компоненты ритма: аврал в ночь перед сдачей — не то же самое,
    что ровная работа две недели, даже при одинаковом объёме кода."""
    burst = make_member(db, team, name="Аврал", role="backend")
    steady = make_member(db, team, name="Ровный", role="backend")
    for _ in range(7):
        make_commit(db, team, burst, days_ago=1, additions=100, deletions=0)
    for day in range(1, 8):
        make_commit(db, team, steady, days_ago=day, additions=100, deletions=0)

    scores = {r["member"].id: r["score"] for r in compute_team_scores(db, [burst, steady], NOW)}
    assert scores[steady.id] > scores[burst.id]


# --- исключение компонент -----------------------------------------------------


def test_team_without_pull_requests_drops_the_review_component(db, team):
    """Регрессия. Команда коммитит прямо в main, ревью не будет никогда —
    компонента должна исчезнуть, а её вес уйти остальным. Раньше она молча
    обнулялась, и все теряли одинаковые 15%."""
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    for m in (a, b):
        make_commit(db, team, m, additions=100)

    assert team_has_reviews(db, team.id) is False
    breakdown = compute_team_scores(db, [a, b], NOW)[0]["breakdown"]
    reviews = next(c for c in breakdown["components"] if c["key"] == "reviews")

    assert reviews["excluded"] is True
    assert reviews["weight"] == 0
    assert "reviews_excluded" in breakdown["notes"]
    # Вес не пропал, а разошёлся по остальным.
    positive = [c for c in breakdown["components"] if c["key"] != "penalty"]
    assert sum(c["weight"] for c in positive) == pytest.approx(SCORE_MAX, abs=0.3)


def test_review_component_returns_once_the_team_uses_pull_requests(db, team):
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    for m in (a, b):
        make_commit(db, team, m, additions=100)
        # Задача с прошедшим сроком, чтобы не исключилась и компонента задач:
        # тогда вес ревью — ровно свой, без перераспределения.
        make_task(db, team, m, status=TaskStatus.done, deadline_days_ago=3, completed_days_ago=4)
    make_pr_review(db, team, a, days_ago=1)

    assert team_has_reviews(db, team.id) is True
    breakdown = compute_team_scores(db, [a, b], NOW)[0]["breakdown"]
    reviews = next(c for c in breakdown["components"] if c["key"] == "reviews")

    assert reviews["excluded"] is False
    assert reviews["weight"] == W_REVIEWS


def test_member_without_tasks_is_not_punished_for_it(db, team):
    """Задач не назначено — это решение тимлида, а не поведение участника.
    Компонента исключается, вес уходит остальным."""
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    for m in (a, b):
        make_commit(db, team, m, additions=100)

    breakdown = compute_team_scores(db, [a, b], NOW)[0]["breakdown"]
    tasks = next(c for c in breakdown["components"] if c["key"] == "tasks")

    assert tasks["excluded"] is True
    assert "tasks_excluded" in breakdown["notes"]


# --- нет данных ---------------------------------------------------------------


def test_has_data_requires_github_or_tasks(db, team):
    m = make_member(db, team, name="Без гита", with_github=False)
    assert get_raw_metrics(db, m, NOW)["has_data"] is False

    make_task(db, team, m)
    assert get_raw_metrics(db, m, NOW)["has_data"] is True


# --- нормализация по роли -----------------------------------------------------


def test_peer_basis_is_team_when_role_has_one_person(db, team):
    """В роли один человек — сравнение идёт по команде, и это видно наружу."""
    backend = make_member(db, team, name="Аня", role="backend")
    frontend = make_member(db, team, name="Боря", role="frontend")
    for m in (backend, frontend):
        make_commit(db, team, m, additions=100)

    results = {r["member"].id: r for r in compute_team_scores(db, [backend, frontend], NOW)}

    assert results[backend.id]["peer_basis"] == "team"
    assert results[backend.id]["role_peer_count"] == 1
    assert "peer_fallback_team" in results[backend.id]["breakdown"]["notes"]


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
    # средний — балл не должен его за это наказывать.
    assert results[d1.id]["peer_basis"] == "role"
    assert results[d1.id]["score"] == results[be1.id]["score"]


def test_members_without_data_do_not_drag_the_median(db, team):
    a = make_member(db, team, name="Аня", role="backend")
    b = make_member(db, team, name="Боря", role="backend")
    ghost = make_member(db, team, name="Призрак", role="backend", with_github=False)
    for m in (a, b):
        make_commit(db, team, m, additions=100)

    results = {r["member"].id: r for r in compute_team_scores(db, [a, b, ghost], NOW)}

    assert results[ghost.id]["score"] is None
    assert results[a.id]["role_peer_count"] == 2  # призрак не считается сравнимым
    assert results[a.id]["score"] == results[b.id]["score"]
