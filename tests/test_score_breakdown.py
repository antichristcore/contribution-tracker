"""Разбор балла: score_breakdown.

Это то, что участник видит в карточке — «откуда взялись эти 65». Разбор и сам
балл считаются одним и тем же кодом, и главный тест здесь ровно об этом:
сумма показанных слагаемых должна давать показанный итог. Разойдутся — и
экран «как это считается» станет врать убедительнее, чем молчание.
"""

import pytest

from backend.app.services.scoring import (
    NORMALIZE_CAP,
    PENALTY_MAX,
    SCORE_MAX,
    W_CODE,
    W_REVIEWS,
    W_RHYTHM,
    W_TASKS,
    contribution_score,
    score_breakdown,
)
from tests.conftest import raw_metrics

PEERS_LINES = [100, 100]
PEERS_REVIEWS = [2, 2]

POSITIVE_KEYS = {"tasks", "code", "rhythm", "reviews"}


def working_member(**overrides):
    base = dict(
        commits_lines_changed_7d=140,
        active_days_14d=5,
        tasks_assigned=5,
        tasks_deadline_eligible=4,
        tasks_completed_on_time=3,
        pr_review_comments_given=2,
        tasks_status_stuck_days_max=1,
    )
    base.update(overrides)
    return raw_metrics(**base)


def component(breakdown, key):
    return next(c for c in breakdown["components"] if c["key"] == key)


def positive_weight(breakdown):
    return sum(c["weight"] for c in breakdown["components"] if c["key"] in POSITIVE_KEYS)


# --- согласованность ----------------------------------------------------------


def test_components_add_up_to_the_score():
    """Читатель складывает столбик глазами — итог обязан сойтись."""
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS)
    total = sum(c["points"] for c in breakdown["components"])

    assert breakdown["score"] == pytest.approx(total, abs=0.5)


def test_breakdown_and_contribution_score_agree():
    raw = working_member()
    breakdown = score_breakdown(raw, PEERS_LINES, PEERS_REVIEWS)

    assert contribution_score(raw, PEERS_LINES, PEERS_REVIEWS) == breakdown["score"]


def test_every_component_is_present_even_when_excluded():
    """Компонента не исчезает из списка — исчезает её вес. Иначе экран не может
    объяснить, почему ревью не считается."""
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS, reviews_available=False)

    keys = [c["key"] for c in breakdown["components"]]
    assert keys == ["tasks", "code", "rhythm", "reviews", "penalty"]


def test_no_data_means_no_breakdown():
    assert score_breakdown(raw_metrics(has_data=False), PEERS_LINES, PEERS_REVIEWS) is None


# --- перераспределение веса ---------------------------------------------------


def test_full_weight_is_one_hundred_when_nothing_is_excluded():
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS)

    assert positive_weight(breakdown) == pytest.approx(SCORE_MAX)
    assert component(breakdown, "tasks")["weight"] == W_TASKS
    assert component(breakdown, "code")["weight"] == W_CODE
    assert component(breakdown, "rhythm")["weight"] == W_RHYTHM
    assert component(breakdown, "reviews")["weight"] == W_REVIEWS


def test_excluded_reviews_hand_their_weight_to_the_others():
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS, reviews_available=False)

    assert component(breakdown, "reviews")["excluded"] is True
    assert component(breakdown, "reviews")["weight"] == 0
    assert positive_weight(breakdown) == pytest.approx(SCORE_MAX, abs=0.3)
    assert component(breakdown, "code")["weight"] > W_CODE


def test_member_without_deadlined_tasks_keeps_the_full_scale():
    """Задач с наступившим сроком нет — компонента исключается, а не считается
    нулём: иначе новичок теряет 40 баллов ни за что."""
    raw = working_member(tasks_deadline_eligible=0, tasks_completed_on_time=0)
    breakdown = score_breakdown(raw, PEERS_LINES, PEERS_REVIEWS)

    assert component(breakdown, "tasks")["excluded"] is True
    assert "tasks_excluded" in breakdown["notes"]
    assert positive_weight(breakdown) == pytest.approx(SCORE_MAX, abs=0.3)


def test_both_components_excluded_still_keeps_the_scale():
    raw = working_member(tasks_deadline_eligible=0, tasks_completed_on_time=0)
    breakdown = score_breakdown(raw, PEERS_LINES, PEERS_REVIEWS, reviews_available=False)

    assert positive_weight(breakdown) == pytest.approx(SCORE_MAX, abs=0.3)
    assert set(breakdown["notes"]) >= {"tasks_excluded", "reviews_excluded"}


# --- частности компонент ------------------------------------------------------


def test_code_component_reports_the_median_it_compared_against():
    """Без медианы нормализованное число необъяснимо: «1.4» само по себе
    ничего не значит."""
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS)
    code = component(breakdown, "code")

    assert code["raw_value"] == 140
    assert code["peer_median"] == 100
    assert code["value"] == pytest.approx(1.4)
    assert code["capped"] is False


def test_code_component_marks_the_cap():
    breakdown = score_breakdown(
        working_member(commits_lines_changed_7d=10_000), PEERS_LINES, PEERS_REVIEWS
    )
    code = component(breakdown, "code")

    assert code["capped"] is True
    assert code["value"] == NORMALIZE_CAP
    assert code["points"] == pytest.approx(W_CODE)
    assert "code_capped" in breakdown["notes"]


def test_tasks_component_shows_the_fraction_behind_the_number():
    breakdown = score_breakdown(working_member(), PEERS_LINES, PEERS_REVIEWS)
    tasks = component(breakdown, "tasks")

    assert (tasks["done_on_time"], tasks["eligible"]) == (3, 4)
    assert tasks["value"] == pytest.approx(0.75)


def test_penalty_is_negative_and_bounded():
    breakdown = score_breakdown(working_member(tasks_status_stuck_days_max=90), PEERS_LINES, PEERS_REVIEWS)
    pen = component(breakdown, "penalty")

    assert pen["points"] == -PENALTY_MAX
    assert pen["stuck_days"] == 90
