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
from backend.app.utils.time import utcnow

COMMIT_WINDOW_DAYS = 7
STUCK_RED_DAYS = 7
YELLOW_STREAK_DAYS = 5
YELLOW_TO_RED_EXTRA_DAYS = 3

# Один коммит не может значить больше этого. Без потолка сгенерированный
# файл (package-lock.json, миграция, вендоренная библиотека) на 10 000 строк
# делает автора "самым полезным человеком в команде" — метрика должна мерить
# работу, а не размер диффа.
MAX_LINES_PER_COMMIT = 1000

# Вклад выше двух медиан дальше не растёт. Иначе одна аномалия улетает в
# lines_norm = 20, score = 7.0 при том, что вся остальная шкала живёт около
# единицы, и правило "на 40% ниже медианы" в маленькой команде начинает
# красить нормальных людей в жёлтый.
NORMALIZE_CAP = 2.0

# Медиана по группе из одного человека — это он сам, нормализация вырождается
# в 1.0. Меньше двух сравнивать не с чем.
MIN_PEER_GROUP = 2

# Веса из спецификации продукта.
W_LINES = 0.35
W_TASKS = 0.35
W_REVIEWS = 0.15
W_PENALTY = 0.15


def get_raw_metrics(db: Session, member: Member, as_of: datetime) -> dict[str, Any]:
    since_7d = as_of - timedelta(days=COMMIT_WINDOW_DAYS)

    commits = (
        db.query(Commit)
        .filter(Commit.member_id == member.id, Commit.authored_at >= since_7d, Commit.authored_at <= as_of)
        .all()
    )
    commits_count_7d = len(commits)
    commits_lines_changed_7d = sum(
        min((c.additions or 0) + (c.deletions or 0), MAX_LINES_PER_COMMIT) for c in commits
    )

    tasks = db.query(Task).filter(Task.assignee_member_id == member.id).all()
    tasks_assigned = len(tasks)
    tasks_completed_on_time = sum(
        1
        for t in tasks
        if t.status == TaskStatus.done and t.completed_at and t.deadline_at and t.completed_at <= t.deadline_at
    )
    open_tasks = [t for t in tasks if t.status != TaskStatus.done]
    stuck_days_list = [max((as_of - t.status_changed_at).days, 0) for t in open_tasks]
    tasks_status_stuck_days_max = max(stuck_days_list) if stuck_days_list else 0

    pr_reviews = (
        db.query(PrReview)
        .filter(
            PrReview.member_id == member.id,
            PrReview.submitted_at.isnot(None),
            PrReview.submitted_at >= since_7d,
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
        "tasks_assigned": tasks_assigned,
        "tasks_completed_on_time": tasks_completed_on_time,
        "tasks_status_stuck_days_max": tasks_status_stuck_days_max,
        "pr_review_comments_given": pr_review_comments_given,
        "last_activity_days_ago": last_activity_days_ago,
        "has_data": has_data,
    }


def normalize(value: float, peer_values: list[float]) -> float:
    """Значение относительно медианы группы, обрезанное сверху NORMALIZE_CAP."""
    peers = [v for v in peer_values if v is not None]
    med = statistics.median(peers) if peers else 0
    if med <= 0:
        return 1.0 if value > 0 else 0.0
    return min(value / med, NORMALIZE_CAP)


def penalty(stuck_days: int) -> float:
    # The spec leaves penalty() unspecified numerically; capping at the red
    # threshold (7 days) keeps it consistent with the red-alert rule below.
    return min(stuck_days / STUCK_RED_DAYS, 1.0)


def contribution_score(
    raw: dict[str, Any], peers_lines_changed: list[float], peers_pr_reviews: list[float]
) -> float | None:
    if not raw["has_data"]:
        return None

    lines_norm = normalize(raw["commits_lines_changed_7d"], peers_lines_changed)
    pr_norm = normalize(raw["pr_review_comments_given"], peers_pr_reviews)
    pen = penalty(raw["tasks_status_stuck_days_max"])
    tasks_assigned = raw["tasks_assigned"]

    if tasks_assigned > 0:
        tasks_ratio = raw["tasks_completed_on_time"] / tasks_assigned
        w_lines, w_tasks, w_reviews = W_LINES, W_TASKS, W_REVIEWS
    else:
        # Задач не назначено — это решение тимлида, а не поведение участника.
        # Считать компоненту нулём значит вычесть 0.35 из score человека,
        # которому просто ещё ничего не дали. Исключаем её и распределяем вес
        # по остальным пропорционально, чтобы сумма весов не менялась.
        tasks_ratio = 0.0
        scale = (W_LINES + W_TASKS + W_REVIEWS) / (W_LINES + W_REVIEWS)
        w_lines, w_tasks, w_reviews = W_LINES * scale, 0.0, W_REVIEWS * scale

    return w_lines * lines_norm + w_tasks * tasks_ratio + w_reviews * pr_norm - W_PENALTY * pen


def role_peer_count(members: list[Member], role: str, has_data_by_id: dict[int, bool]) -> int:
    """Сколько человек в этой роли вообще сравнимы (есть данные)."""
    return sum(1 for m in members if m.role_in_team == role and has_data_by_id.get(m.id))


def compute_team_scores(db: Session, members: list[Member], as_of: datetime) -> list[dict[str, Any]]:
    raw_by_member = {m.id: get_raw_metrics(db, m, as_of) for m in members}
    has_data_by_id = {m.id: raw_by_member[m.id]["has_data"] for m in members}

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
        score = contribution_score(raw, peers_lines, peers_pr)
        results.append(
            {
                "member": m,
                "raw": raw,
                "score": score,
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
