"""Диагностика «не может» против «не делает»: diagnose.

Это то, чем продукт отличается от обычного счётчика коммитов. Формулировки
здесь важнее чисел: система показывает факт, а не выносит приговор человеку.
"""

from backend.app.services.scoring import diagnose
from tests.conftest import raw_metrics


def test_activity_plus_stalled_task_means_stuck():
    """Коммиты идут, а задача не закрывается — человек застрял, а не забил."""
    result = diagnose(
        raw_metrics(commits_count_7d=6, tasks_status_stuck_days_max=4, tasks_assigned=2)
    )

    assert result is not None
    assert result.label == "stuck"


def test_reviews_alone_count_as_activity():
    """Ревьюер без коммитов всё равно работает — это «застрял», а не «пропал»."""
    result = diagnose(
        raw_metrics(pr_review_comments_given=3, tasks_status_stuck_days_max=5, tasks_assigned=1)
    )

    assert result is not None
    assert result.label == "stuck"


def test_stall_under_three_days_is_not_a_diagnosis_yet():
    """Задача стоит два дня — это ещё нормальная работа, повода для ярлыка нет."""
    assert diagnose(raw_metrics(commits_count_7d=6, tasks_status_stuck_days_max=2)) is None


def test_total_silence_with_open_tasks_means_disengaged():
    result = diagnose(
        raw_metrics(
            commits_count_7d=0,
            pr_review_comments_given=0,
            last_activity_days_ago=9,
            tasks_assigned=3,
            tasks_completed_on_time=0,
        )
    )

    assert result is not None
    assert result.label == "disengaged"


def test_never_active_member_is_disengaged():
    """last_activity_days_ago = None — активности не было ни разу."""
    result = diagnose(
        raw_metrics(last_activity_days_ago=None, tasks_assigned=2, tasks_completed_on_time=0)
    )

    assert result is not None
    assert result.label == "disengaged"


def test_silence_after_finishing_everything_is_not_a_diagnosis():
    """Все задачи закрыты — молчание не проблема, ярлык не нужен."""
    assert (
        diagnose(
            raw_metrics(last_activity_days_ago=10, tasks_assigned=3, tasks_completed_on_time=3)
        )
        is None
    )


def test_stuck_wins_over_disengaged():
    """Если признаки пересеклись, «застрял» приоритетнее: он ведёт к помощи,
    а «забил» — к личному разговору. Ошибиться в эту сторону дешевле."""
    result = diagnose(
        raw_metrics(
            commits_count_7d=2,
            tasks_status_stuck_days_max=6,
            last_activity_days_ago=5,
            tasks_assigned=3,
            tasks_completed_on_time=0,
        )
    )

    assert result is not None
    assert result.label == "stuck"


def test_healthy_member_gets_no_label():
    """Нормально работающий человек не получает никакого диагноза вообще."""
    assert (
        diagnose(
            raw_metrics(
                commits_count_7d=8,
                tasks_assigned=4,
                tasks_completed_on_time=4,
                last_activity_days_ago=0,
            )
        )
        is None
    )


def test_no_diagnosis_without_data():
    """По участнику без данных нельзя сказать ничего — и система молчит."""
    assert diagnose(raw_metrics(has_data=False, commits_count_7d=0)) is None


def test_distracted_case_is_not_implemented_yet():
    """Зафиксированный пробел, а не забытый тест.

    Спецификация описывает три случая, diagnose() реализует два. Третий —
    «коммиты есть, но по не своим задачам» — сейчас не даёт никакого диагноза:
    участник с активностью и без застоя просто проходит мимо всех веток.

    Спека на правило: docs/task-sa.md, задача 3. Когда его реализуют, этот
    тест должен покраснеть — и это будет сигналом переписать его на проверку
    label == "distracted", а не удалить.
    """
    active_but_off_plan = raw_metrics(
        commits_count_7d=9,
        tasks_status_stuck_days_max=0,
        tasks_assigned=2,
        tasks_completed_on_time=0,
        last_activity_days_ago=0,
    )

    assert diagnose(active_but_off_plan) is None


def test_explanations_do_not_judge_the_person():
    """Тексты диагнозов не должны содержать оценок человека — инструмент
    обязан оставаться источником фактов, а не конфликта."""
    forbidden = ("плохой", "ленив", "виноват", "бездельник", "хуже")

    stuck = diagnose(raw_metrics(commits_count_7d=5, tasks_status_stuck_days_max=4))
    disengaged = diagnose(
        raw_metrics(last_activity_days_ago=8, tasks_assigned=2, tasks_completed_on_time=0)
    )

    for result in (stuck, disengaged):
        assert result is not None
        lowered = result.explanation.lower()
        assert not any(word in lowered for word in forbidden), result.explanation
