"""Расчёт вклада участника. Шкала — целые 0..100.

Балл собирается из четырёх положительных компонент и одного штрафа. Две
компоненты абсолютные (задачи в срок, ритм) — они говорят, что человек
сделал. Две относительные (код, ревью) — они сравнивают его с медианой
команды: «много строк» не значит ничего в отрыве от того, сколько пишут
остальные.

Главное правило, без которого формула врёт: компонента, по которой у команды
нет данных, **исключается**, а её вес пропорционально уходит остальным.
Обнулять её нельзя — это молча вычитает баллы у всех сразу. Команда, которая
коммитит прямо в main без PR (наш случай), не должна поголовно терять вес
ревью; человек, которому ещё не назначили задач, не должен терять вес задач.

Ориентир по шкале: ~50 — обычный рабочий уровень, 100 — всё сдано в срок,
ровный ритм и вклад в код вдвое выше медианы команды.
"""

import math
import statistics
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models import (
    Commit,
    Member,
    PrReview,
    ScoreHistory,
    StatusColor,
    Task,
    TaskStatus,
    TaskStatusHistory,
)
from backend.app.schemas import DiagnosisOut

SCORE_MAX = 100

# Веса компонент в баллах итоговой шкалы. Положительные в сумме дают 100,
# штраф вычитается сверх них.
W_TASKS = 40
W_CODE = 35
W_RHYTHM = 15
W_REVIEWS = 10
PENALTY_MAX = 20

# Окно активности по коду.
CODE_WINDOW_DAYS = 7
# Ритм смотрит шире: две недели, чтобы отличить ровную работу от аврала
# в ночь перед сдачей. Столько дней с коммитами даёт полный балл за ритм.
RHYTHM_WINDOW_DAYS = 14
RHYTHM_TARGET_DAYS = 7

STUCK_RED_DAYS = 7
YELLOW_STREAK_DAYS = 5
YELLOW_TO_RED_EXTRA_DAYS = 3

# Один коммит не может значить больше этого. Без потолка сгенерированный
# файл (package-lock.json, миграция, вендоренная библиотека) на 10 000 строк
# делает автора "самым полезным человеком в команде" — метрика должна мерить
# работу, а не размер диффа.
MAX_LINES_PER_COMMIT = 1000

# Вклад выше двух медиан дальше не растёт. Иначе одна аномалия улетает в
# norm = 20, и правило "на 40% ниже медианы" в маленькой команде начинает
# красить нормальных людей в жёлтый.
NORMALIZE_CAP = 2.0

# Медиана по группе из одного человека — это он сам, нормализация вырождается
# в 1.0. Меньше двух сравнивать не с чем.
MIN_PEER_GROUP = 2


def active_days(db: Session, member_id: int, as_of: datetime, window_days: int) -> int:
    """Сколько разных дней в окне были с коммитами.

    Отдельный запрос, а не подсчёт по уже выбранным коммитам: окно ритма шире
    окна кода, и тянуть ради этого две недели коммитов в память незачем.
    """
    since = (as_of - timedelta(days=window_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = (
        db.query(func.date(Commit.authored_at))
        .filter(
            Commit.member_id == member_id,
            Commit.authored_at >= since,
            Commit.authored_at <= as_of,
        )
        .distinct()
        .all()
    )
    return len(rows)


def get_raw_metrics(db: Session, member: Member, as_of: datetime) -> dict[str, Any]:
    since_code = as_of - timedelta(days=CODE_WINDOW_DAYS)

    commits = (
        db.query(Commit)
        .filter(Commit.member_id == member.id, Commit.authored_at >= since_code, Commit.authored_at <= as_of)
        .all()
    )
    commits_count_7d = len(commits)
    commits_lines_changed_7d = sum(
        min((c.additions or 0) + (c.deletions or 0), MAX_LINES_PER_COMMIT) for c in commits
    )

    tasks = db.query(Task).filter(Task.assignee_member_id == member.id).all()
    tasks_assigned = len(tasks)

    # В долю "в срок" попадают только задачи, по которым срок уже наступил или
    # работа закончена. Задача без дедлайна не попадает никуда: дедлайн не
    # проставил тимлид, наказывать за это исполнителя не за что. Задача с
    # дедлайном в будущем ещё в работе — она не провал и не успех.
    eligible = [
        t
        for t in tasks
        if t.deadline_at and (t.status == TaskStatus.done or t.deadline_at < as_of)
    ]
    tasks_deadline_eligible = len(eligible)
    # Сравнение по дню, а не по секунде: дедлайн обычно стоит на полночь, и
    # задача, сданная в день дедлайна днём, формально оказывалась просроченной.
    tasks_completed_on_time = sum(
        1
        for t in eligible
        if t.status == TaskStatus.done
        and t.completed_at
        and t.completed_at.date() <= t.deadline_at.date()
    )

    open_tasks = [t for t in tasks if t.status != TaskStatus.done]
    stuck_days_list = [max((as_of - t.status_changed_at).days, 0) for t in open_tasks]
    tasks_status_stuck_days_max = max(stuck_days_list) if stuck_days_list else 0

    pr_reviews = (
        db.query(PrReview)
        .filter(
            PrReview.member_id == member.id,
            PrReview.submitted_at.isnot(None),
            PrReview.submitted_at >= since_code,
            PrReview.submitted_at <= as_of,
        )
        .all()
    )
    pr_review_comments_given = len(pr_reviews)

    last_activity_candidates: list[int] = []
    last_commit = (
        db.query(Commit).filter(Commit.member_id == member.id).order_by(Commit.authored_at.desc()).first()
    )
    if last_commit:
        last_activity_candidates.append(max((as_of - last_commit.authored_at).days, 0))
    last_status_change = (
        db.query(TaskStatusHistory)
        .filter(TaskStatusHistory.changed_by_member_id == member.id)
        .order_by(TaskStatusHistory.changed_at.desc())
        .first()
    )
    if last_status_change:
        last_activity_candidates.append(max((as_of - last_status_change.changed_at).days, 0))
    last_review = (
        db.query(PrReview)
        .filter(PrReview.member_id == member.id, PrReview.submitted_at.isnot(None))
        .order_by(PrReview.submitted_at.desc())
        .first()
    )
    if last_review and last_review.submitted_at:
        last_activity_candidates.append(max((as_of - last_review.submitted_at).days, 0))

    last_activity_days_ago = min(last_activity_candidates) if last_activity_candidates else None

    has_data = member.github_mapping is not None or tasks_assigned > 0

    return {
        "commits_count_7d": commits_count_7d,
        "commits_lines_changed_7d": commits_lines_changed_7d,
        "active_days_14d": active_days(db, member.id, as_of, RHYTHM_WINDOW_DAYS),
        "tasks_assigned": tasks_assigned,
        "tasks_deadline_eligible": tasks_deadline_eligible,
        "tasks_completed_on_time": tasks_completed_on_time,
        "tasks_status_stuck_days_max": tasks_status_stuck_days_max,
        "pr_review_comments_given": pr_review_comments_given,
        "last_activity_days_ago": last_activity_days_ago,
        "has_data": has_data,
    }


def peer_median(peer_values: list[float]) -> float:
    peers = [v for v in peer_values if v is not None]
    return statistics.median(peers) if peers else 0


def normalize(value: float, peer_values: list[float]) -> float:
    """Значение относительно медианы группы, обрезанное сверху NORMALIZE_CAP.
    Медиана даёт ровно 1.0, потолок — 2.0."""
    med = peer_median(peer_values)
    if med <= 0:
        return 1.0 if value > 0 else 0.0
    return min(value / med, NORMALIZE_CAP)


def _round_half_up(value: float) -> int:
    """Обычное школьное округление. round() в Python округляет 64.5 к чётному,
    и итог расходился бы с суммой слагаемых, которую читатель складывает глазами."""
    return math.floor(value + 0.5)


def penalty(stuck_days: int) -> float:
    """Доля штрафа: 0 при отсутствии застоя, 1.0 на красном пороге и дальше."""
    return min(stuck_days / STUCK_RED_DAYS, 1.0)


def score_breakdown(
    raw: dict[str, Any],
    peers_lines_changed: list[float],
    peers_pr_reviews: list[float],
    reviews_available: bool = True,
) -> dict[str, Any] | None:
    """Единственное место, где считается вклад.

    Возвращает и итог, и все промежуточные величины — интерфейс показывает
    именно их, поэтому показанное не может разойтись с посчитанным.
    `contribution_score()` — тонкая обёртка над `["score"]`.
    """
    if not raw["has_data"]:
        return None

    notes: list[str] = []

    # --- задачи: доля закрытых в срок среди тех, по которым срок уже наступил
    eligible = raw["tasks_deadline_eligible"]
    tasks_excluded = eligible == 0
    tasks_value = (raw["tasks_completed_on_time"] / eligible) if eligible else None
    if tasks_excluded:
        notes.append("tasks_excluded")

    # --- код: строки относительно медианы, медиана = половина веса
    code_median = peer_median(peers_lines_changed)
    code_norm = normalize(raw["commits_lines_changed_7d"], peers_lines_changed)
    code_capped = code_norm >= NORMALIZE_CAP
    if code_capped:
        notes.append("code_capped")

    # --- ритм: сколько дней из окна были с коммитами
    rhythm_value = min(raw["active_days_14d"] / RHYTHM_TARGET_DAYS, 1.0)

    # --- ревью: если в команде нет ни одного ревью, компоненты просто нет
    reviews_median = peer_median(peers_pr_reviews)
    reviews_norm = normalize(raw["pr_review_comments_given"], peers_pr_reviews)
    if not reviews_available:
        notes.append("reviews_excluded")

    # Вес исключённых компонент пропорционально уходит остальным, чтобы сумма
    # положительных весов всегда оставалась SCORE_MAX.
    base = {"tasks": W_TASKS, "code": W_CODE, "rhythm": W_RHYTHM, "reviews": W_REVIEWS}
    excluded = {"tasks": tasks_excluded, "code": False, "rhythm": False, "reviews": not reviews_available}
    kept = sum(w for key, w in base.items() if not excluded[key])
    scale = (SCORE_MAX / kept) if kept else 0.0
    weight = {key: (0.0 if excluded[key] else base[key] * scale) for key in base}

    components = [
        {
            "key": "tasks",
            "weight": round(weight["tasks"], 1),
            "value": tasks_value,
            "points": round(weight["tasks"] * (tasks_value or 0.0), 1),
            "excluded": tasks_excluded,
            "done_on_time": raw["tasks_completed_on_time"],
            "eligible": eligible,
            "assigned": raw["tasks_assigned"],
        },
        {
            "key": "code",
            "weight": round(weight["code"], 1),
            "value": code_norm,
            "points": round(weight["code"] * code_norm / NORMALIZE_CAP, 1),
            "excluded": False,
            "raw_value": raw["commits_lines_changed_7d"],
            "peer_median": code_median,
            "capped": code_capped,
        },
        {
            "key": "rhythm",
            "weight": round(weight["rhythm"], 1),
            "value": rhythm_value,
            "points": round(weight["rhythm"] * rhythm_value, 1),
            "excluded": False,
            "active_days": raw["active_days_14d"],
            "target_days": RHYTHM_TARGET_DAYS,
            "window_days": RHYTHM_WINDOW_DAYS,
        },
        {
            "key": "reviews",
            "weight": round(weight["reviews"], 1),
            "value": None if not reviews_available else reviews_norm,
            "points": round(weight["reviews"] * reviews_norm / NORMALIZE_CAP, 1) if reviews_available else 0.0,
            "excluded": not reviews_available,
            "raw_value": raw["pr_review_comments_given"],
            "peer_median": reviews_median,
        },
    ]

    pen = penalty(raw["tasks_status_stuck_days_max"])
    components.append(
        {
            "key": "penalty",
            "weight": -PENALTY_MAX,
            "value": pen,
            "points": -round(PENALTY_MAX * pen, 1),
            "excluded": False,
            "stuck_days": raw["tasks_status_stuck_days_max"],
            "red_days": STUCK_RED_DAYS,
        }
    )

    total = sum(c["points"] for c in components)
    score = max(0, min(SCORE_MAX, _round_half_up(total)))

    return {"score": score, "components": components, "notes": notes}


def contribution_score(
    raw: dict[str, Any],
    peers_lines_changed: list[float],
    peers_pr_reviews: list[float],
    reviews_available: bool = True,
) -> int | None:
    breakdown = score_breakdown(raw, peers_lines_changed, peers_pr_reviews, reviews_available)
    return breakdown["score"] if breakdown else None


def role_peer_count(members: list[Member], role: str, has_data_by_id: dict[int, bool]) -> int:
    """Сколько человек в этой роли вообще сравнимы (есть данные)."""
    return sum(1 for m in members if m.role_in_team == role and has_data_by_id.get(m.id))


def team_has_reviews(db: Session, team_id: int) -> bool:
    """Есть ли у команды хоть одно ревью за всю историю.

    Проверка не по окну: команда, сделавшая ревью в прошлом месяце, не должна
    то терять компоненту, то получать её обратно каждую неделю.
    """
    return db.query(PrReview.id).filter(PrReview.team_id == team_id).first() is not None


def compute_team_scores(db: Session, members: list[Member], as_of: datetime) -> list[dict[str, Any]]:
    raw_by_member = {m.id: get_raw_metrics(db, m, as_of) for m in members}
    has_data_by_id = {m.id: raw_by_member[m.id]["has_data"] for m in members}
    reviews_available = team_has_reviews(db, members[0].team_id) if members else False

    def peer_group(metric: str, role: str) -> tuple[list[float], str]:
        """Значения для сравнения + на чём сравниваем: "role" или "team".

        Спецификация просит нормализовать внутри роли, но в студенческой команде
        роль обычно занята одним человеком — медиана по группе из одного даёт
        ровно 1.0 и сравнение теряет смысл. Тогда честнее откатиться на всю
        команду и сказать об этом наружу (peer_basis), а не делать вид, что
        нормализация по роли отработала.
        """
        same_role = [
            raw_by_member[m.id][metric]
            for m in members
            if m.role_in_team == role and raw_by_member[m.id]["has_data"]
        ]
        if len(same_role) >= MIN_PEER_GROUP:
            return same_role, "role"
        return [raw_by_member[m.id][metric] for m in members if raw_by_member[m.id]["has_data"]], "team"

    results = []
    for m in members:
        raw = raw_by_member[m.id]
        peers_lines, basis = peer_group("commits_lines_changed_7d", m.role_in_team)
        peers_pr, _ = peer_group("pr_review_comments_given", m.role_in_team)
        breakdown = score_breakdown(raw, peers_lines, peers_pr, reviews_available)
        if breakdown and basis == "team":
            breakdown["notes"].append("peer_fallback_team")
        results.append(
            {
                "member": m,
                "raw": raw,
                "score": breakdown["score"] if breakdown else None,
                "breakdown": breakdown,
                "peer_basis": basis,
                "role_peer_count": role_peer_count(members, m.role_in_team, has_data_by_id),
            }
        )
    return results


def diagnose(raw: dict[str, Any]) -> DiagnosisOut | None:
    if not raw["has_data"]:
        return None

    has_activity = raw["commits_count_7d"] > 0 or raw["pr_review_comments_given"] > 0
    is_stalled = raw["tasks_status_stuck_days_max"] >= 3
    no_activity_at_all = (
        raw["commits_count_7d"] == 0
        and raw["pr_review_comments_given"] == 0
        and (raw["last_activity_days_ago"] is None or raw["last_activity_days_ago"] >= 4)
    )

    if has_activity and is_stalled:
        return DiagnosisOut(
            label="stuck",
            explanation="Есть активность (коммиты/ревью), но задача не завершается — возможно, участник застрял.",
        )
    if no_activity_at_all and raw["tasks_assigned"] > raw["tasks_completed_on_time"]:
        return DiagnosisOut(
            label="disengaged",
            explanation="Активности не видно совсем — стоит поговорить лично, а не слать автоматический пуш.",
        )
    return None


def _team_median_score_for_date(db: Session, team_id: int, target_date) -> float | None:
    rows = (
        db.query(ScoreHistory)
        .filter(
            ScoreHistory.team_id == team_id,
            ScoreHistory.has_data.is_(True),
            func.date(ScoreHistory.computed_at) == target_date,
        )
        .all()
    )
    scores = [r.contribution_score for r in rows if r.contribution_score is not None]
    return statistics.median(scores) if scores else None


def _member_at_risk_on_date(db: Session, team_id: int, member_id: int, target_date) -> bool | None:
    row = (
        db.query(ScoreHistory)
        .filter(
            ScoreHistory.team_id == team_id,
            ScoreHistory.member_id == member_id,
            func.date(ScoreHistory.computed_at) == target_date,
        )
        .order_by(ScoreHistory.computed_at.desc())
        .first()
    )
    if not row or not row.has_data:
        return None

    median = _team_median_score_for_date(db, team_id, target_date)
    below_median = median is not None and median > 0 and (row.contribution_score or 0) < median * 0.6
    stale_activity = (
        row.last_activity_days_ago is not None
        and row.last_activity_days_ago >= 4
        and row.tasks_assigned > row.tasks_completed_on_time
    )
    return bool(below_median or stale_activity)


def evaluate_thresholds(db: Session, team_id: int, member_id: int, as_of: datetime) -> StatusColor:
    today = as_of.date()

    latest = (
        db.query(ScoreHistory)
        .filter(
            ScoreHistory.team_id == team_id,
            ScoreHistory.member_id == member_id,
            func.date(ScoreHistory.computed_at) == today,
        )
        .order_by(ScoreHistory.computed_at.desc())
        .first()
    )
    if not latest or not latest.has_data:
        return StatusColor.no_data
    if latest.tasks_status_stuck_days_max >= STUCK_RED_DAYS:
        return StatusColor.red

    window = YELLOW_STREAK_DAYS + YELLOW_TO_RED_EXTRA_DAYS
    risk_flags = [
        _member_at_risk_on_date(db, team_id, member_id, today - timedelta(days=i)) for i in range(window)
    ]

    yellow_streak = all(flag is True for flag in risk_flags[:YELLOW_STREAK_DAYS])
    if not yellow_streak:
        return StatusColor.green

    red_streak = all(flag is True for flag in risk_flags[:window])
    return StatusColor.red if red_streak else StatusColor.yellow
