"""Пороги «зелёный / жёлтый / красный / нет данных»: evaluate_thresholds.

Сердце продукта. Именно эта функция решает, получит ли живой человек
уведомление, поэтому границы проверяются с обеих сторон — и там, где сигнал
обязан сработать, и там, где обязан промолчать.

Правила из спецификации:
  - застой по любой открытой задаче >= 7 дней -> сразу красный;
  - «риск» в день = score ниже медианы команды на 40%+ ИЛИ
    последняя активность >= 4 дней при незакрытых задачах;
  - риск 5 дней подряд -> жёлтый; риск все 8 дней -> красный.
"""

import pytest

from backend.app.models import StatusColor
from backend.app.services.scoring import (
    STUCK_RED_DAYS,
    YELLOW_STREAK_DAYS,
    YELLOW_TO_RED_EXTRA_DAYS,
    evaluate_thresholds,
)
from tests.conftest import NOW, make_member, make_score_row

WINDOW = YELLOW_STREAK_DAYS + YELLOW_TO_RED_EXTRA_DAYS  # 8 дней истории
HEALTHY = 1.0
RISKY = 0.3  # ниже медианы 1.0 более чем на 40%


@pytest.fixture
def crew(db, team):
    """Участник под наблюдением плюс двое здоровых коллег: медиана команды
    считается по всем троим, поэтому одиночку не с кем сравнивать."""
    watched = make_member(db, team, name="Watched")
    peers = [make_member(db, team, name="Peer1"), make_member(db, team, name="Peer2")]
    return watched, peers


def seed_peers(db, team, peers, days=WINDOW):
    for day in range(days):
        for p in peers:
            make_score_row(db, team, p, day, HEALTHY)


def check(db, team, member):
    return evaluate_thresholds(db, team.id, member.id, NOW)


# --- нет данных --------------------------------------------------------------


def test_no_history_means_no_data(db, team, crew):
    watched, peers = crew
    seed_peers(db, team, peers)

    assert check(db, team, watched) is StatusColor.no_data


def test_row_without_data_flag_means_no_data(db, team, crew):
    """Участник без привязанного GitHub — «нет данных», а не зелёный."""
    watched, peers = crew
    seed_peers(db, team, peers)
    make_score_row(db, team, watched, 0, None, has_data=False)

    assert check(db, team, watched) is StatusColor.no_data


def test_no_data_wins_over_stuck_task(db, team, crew):
    """Даже застрявшая задача не красит в красный того, по кому нет данных —
    иначе тимлид получит уведомление, которое нечем объяснить."""
    watched, peers = crew
    seed_peers(db, team, peers)
    make_score_row(db, team, watched, 0, None, has_data=False, stuck_days=30)

    assert check(db, team, watched) is StatusColor.no_data


# --- красный по застрявшей задаче -------------------------------------------


@pytest.mark.parametrize(
    "stuck_days, expected",
    [
        (STUCK_RED_DAYS - 1, StatusColor.green),
        (STUCK_RED_DAYS, StatusColor.red),
        (STUCK_RED_DAYS + 10, StatusColor.red),
    ],
)
def test_stuck_task_threshold_boundary(db, team, crew, stuck_days, expected):
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, HEALTHY, stuck_days=stuck_days if day == 0 else 0)

    assert check(db, team, watched) is expected


def test_stuck_task_reds_even_a_top_performer(db, team, crew):
    """«Много коммитит» не отменяет того, что задача не двигается неделю."""
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, 5.0, stuck_days=STUCK_RED_DAYS if day == 0 else 0)

    assert check(db, team, watched) is StatusColor.red


# --- серии риска -------------------------------------------------------------


def test_equal_team_is_green(db, team, crew):
    """Ровная команда не должна порождать ни одного жёлтого."""
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, HEALTHY)

    assert check(db, team, watched) is StatusColor.green


@pytest.mark.parametrize(
    "risky_days, expected, case",
    [
        (0, StatusColor.green, "нет просадки"),
        (YELLOW_STREAK_DAYS - 1, StatusColor.green, "4 дня — ещё рано"),
        (YELLOW_STREAK_DAYS, StatusColor.yellow, "5 дней — жёлтый"),
        (WINDOW - 1, StatusColor.yellow, "7 дней — всё ещё жёлтый"),
        (WINDOW, StatusColor.red, "8 дней подряд — красный"),
    ],
)
def test_risk_streak_boundaries(db, team, crew, risky_days, expected, case):
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, RISKY if day < risky_days else HEALTHY)

    assert check(db, team, watched) is expected, case


def test_recovery_breaks_the_streak(db, team, crew):
    """Человек просел неделю, потом вернулся — сегодня он снова зелёный.

    Серия считается от сегодняшнего дня назад, так что свежий здоровый день
    обязан обнулить накопленное.
    """
    watched, peers = crew
    seed_peers(db, team, peers)
    make_score_row(db, team, watched, 0, HEALTHY)
    for day in range(1, WINDOW):
        make_score_row(db, team, watched, day, RISKY)

    assert check(db, team, watched) is StatusColor.green


def test_missing_day_breaks_the_streak(db, team, crew):
    """Пропуск в истории (сервер лежал, синк не отработал) не должен
    достраиваться до красного — недостающий день рвёт серию."""
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        if day == 3:
            continue
        make_score_row(db, team, watched, day, RISKY)

    assert check(db, team, watched) is StatusColor.green


# --- граница правила «на 40% ниже медианы» ----------------------------------


@pytest.mark.parametrize(
    "score, expected, case",
    [
        (0.6, StatusColor.green, "ровно на 40% ниже — ещё не риск"),
        (0.59, StatusColor.yellow, "чуть ниже границы — риск"),
    ],
)
def test_forty_percent_below_median_boundary(db, team, crew, score, expected, case):
    watched, peers = crew
    seed_peers(db, team, peers)
    # Просадку держим ровно YELLOW_STREAK_DAYS, а не весь WINDOW: иначе тест
    # проверял бы не границу «40% ниже медианы», а длину серии, и при любом
    # рискованном score получал бы красный (см. test_risk_streak_boundaries).
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, score if day < YELLOW_STREAK_DAYS else HEALTHY)

    assert check(db, team, watched) is expected, case


# --- второй путь к риску: тишина при открытых задачах ------------------------


def test_silence_with_open_tasks_is_risk_even_with_median_score(db, team, crew):
    """Второе условие жёлтого из PROJECT.md: активности нет 4+ дня, а задачи висят.

    Score при этом может быть нормальным — например, человек хорошо закрыл
    прошлую неделю и с тех пор пропал.
    """
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        risky = day < YELLOW_STREAK_DAYS
        make_score_row(
            db,
            team,
            watched,
            day,
            HEALTHY,
            last_activity_days_ago=5 if risky else 0,
            tasks_assigned=2,
            tasks_completed_on_time=0,
        )

    assert check(db, team, watched) is StatusColor.yellow


def test_silence_without_open_tasks_is_not_risk(db, team, crew):
    """Всё сдал и ушёл отдыхать — это не повод для сигнала."""
    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(
            db,
            team,
            watched,
            day,
            HEALTHY,
            last_activity_days_ago=10,
            tasks_assigned=3,
            tasks_completed_on_time=3,
        )

    assert check(db, team, watched) is StatusColor.green


def test_another_teams_scores_do_not_affect_median(db, team, crew):
    """Медиана считается внутри команды. Чужая команда не должна на неё влиять."""
    from tests.conftest import make_team

    watched, peers = crew
    seed_peers(db, team, peers)
    for day in range(WINDOW):
        make_score_row(db, team, watched, day, HEALTHY)

    other = make_team(db, name="Чужая команда")
    stranger = make_member(db, other, name="Stranger")
    for day in range(WINDOW):
        make_score_row(db, other, stranger, day, 100.0)

    assert check(db, team, watched) is StatusColor.green
