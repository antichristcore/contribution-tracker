import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.deps import get_current_member, get_db, require_teamlead
from backend.app.models import Commit, Member, ScoreHistory, StatusColor, SystemRole, Team
from backend.app.schemas import CommitOut, ScoreHistoryOut, TeamSummaryMemberOut, TeamSummaryOut
from backend.app.services import scoring
from backend.app.services.recalc import recalculate_team_scores
from backend.app.services.task_utils import commits_to_out
from backend.app.utils.time import utcnow

router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("/history", response_model=list[ScoreHistoryOut])
def score_history(
    member_id: int,
    days: int = 21,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> list[ScoreHistory]:
    target = db.get(Member, member_id)
    if not target or target.team_id != current.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if current.system_role.value != "teamlead" and current.id != member_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    since = utcnow() - timedelta(days=days)
    return (
        db.query(ScoreHistory)
        .filter(ScoreHistory.member_id == member_id, ScoreHistory.computed_at >= since)
        .order_by(ScoreHistory.computed_at.asc())
        .all()
    )


@router.get("/team-summary", response_model=TeamSummaryOut)
def team_summary(
    db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> TeamSummaryOut:
    # Тимлид считается наравне со всеми: он тоже коммитит, и его карточка
    # стоит в том же списке под пульсом. Полоска обязана сходиться с тем, что
    # человек видит под ней.
    members = (
        db.query(Member)
        .filter(Member.team_id == teamlead.team_id, Member.is_active.is_(True))
        .all()
    )
    rows = []
    scores = []
    counts = {StatusColor.green: 0, StatusColor.yellow: 0, StatusColor.red: 0, StatusColor.no_data: 0}
    for m in members:
        latest = (
            db.query(ScoreHistory)
            .filter(ScoreHistory.member_id == m.id)
            .order_by(ScoreHistory.computed_at.desc())
            .first()
        )
        color = latest.status_color if latest else StatusColor.no_data
        score = latest.contribution_score if latest else None
        counts[color] = counts.get(color, 0) + 1
        if score is not None:
            scores.append(score)
        rows.append(TeamSummaryMemberOut(member_id=m.id, display_name=m.display_name, status_color=color, contribution_score=score))

    return TeamSummaryOut(
        median_score=statistics.median(scores) if scores else None,
        green_count=counts[StatusColor.green],
        yellow_count=counts[StatusColor.yellow],
        red_count=counts[StatusColor.red],
        no_data_count=counts[StatusColor.no_data],
        members=rows,
    )


@router.post("/recalculate")
async def recalculate(
    as_of: datetime | None = None,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> list[dict]:
    if as_of is not None:
        if not settings.DEV_TIME_TRAVEL:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "as_of is only allowed with DEV_TIME_TRAVEL enabled")
        if as_of.tzinfo is not None:
            as_of = as_of.astimezone(timezone.utc).replace(tzinfo=None)
    team = db.get(Team, teamlead.team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return await recalculate_team_scores(db, team, as_of)


class CommitActivityDay(BaseModel):
    date: str
    commits: int
    lines: int


class CommitActivityOut(BaseModel):
    days: list[CommitActivityDay]
    max_commits: int
    total_commits: int
    total_lines: int


@router.get("/commit-activity", response_model=CommitActivityOut)
def commit_activity(
    member_id: int | None = None,
    days: int = 91,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> CommitActivityOut:
    """Коммиты по дням — для календаря активности в стиле GitHub.

    Возвращает сплошной ряд дней без пропусков: клетки без коммитов тоже
    нужны, иначе календарь не построить.
    """
    days = max(7, min(days, 366))
    until = utcnow()
    since = until - timedelta(days=days - 1)

    query = db.query(Commit).filter(
        Commit.team_id == current.team_id,
        Commit.authored_at >= since.replace(hour=0, minute=0, second=0, microsecond=0),
        Commit.authored_at <= until,
    )
    if member_id is not None:
        query = query.filter(Commit.member_id == member_id)

    buckets: dict[str, list[int]] = {}
    for commit in query.all():
        key = commit.authored_at.date().isoformat()
        slot = buckets.setdefault(key, [0, 0])
        slot[0] += 1
        slot[1] += (commit.additions or 0) + (commit.deletions or 0)

    out: list[CommitActivityDay] = []
    for offset in range(days):
        day = (since + timedelta(days=offset)).date().isoformat()
        commits, lines = buckets.get(day, (0, 0))
        out.append(CommitActivityDay(date=day, commits=commits, lines=lines))

    return CommitActivityOut(
        days=out,
        max_commits=max((d.commits for d in out), default=0),
        total_commits=sum(d.commits for d in out),
        total_lines=sum(d.lines for d in out),
    )


@router.get("/commit-activity/day", response_model=list[CommitOut])
def commit_activity_day(
    date: str,
    member_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> list[CommitOut]:
    """Коммиты за один день календаря — то, что открывается тапом по клетке.

    Границы дня те же naive-UTC сутки, по которым /commit-activity раскладывает
    клетки, поэтому список не может разойтись со счётчиком на клетке.
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date must be YYYY-MM-DD")

    query = db.query(Commit).filter(
        Commit.team_id == current.team_id,
        Commit.authored_at >= day,
        Commit.authored_at < day + timedelta(days=1),
    )
    if member_id is not None:
        query = query.filter(Commit.member_id == member_id)

    commits = query.order_by(Commit.authored_at.desc()).limit(max(1, min(limit, 200))).all()
    return commits_to_out(db, commits, db.get(Team, current.team_id))


class ScoreFormulaOut(BaseModel):
    """Константы формулы для экрана «Как считается вклад».

    Экран рендерится из этих чисел, а не из захардкоженной копии: иначе текст
    разъедется с кодом и снова придётся объяснять балл на словах.
    """

    score_max: int
    weight_tasks: int
    weight_code: int
    weight_rhythm: int
    weight_reviews: int
    penalty_max: int
    code_window_days: int
    rhythm_window_days: int
    rhythm_target_days: int
    normalize_cap: float
    max_lines_per_commit: int
    stuck_red_days: int
    yellow_streak_days: int
    yellow_to_red_extra_days: int
    yellow_below_median_percent: int
    yellow_inactive_days: int


@router.get("/formula", response_model=ScoreFormulaOut)
def score_formula() -> ScoreFormulaOut:
    return ScoreFormulaOut(
        score_max=scoring.SCORE_MAX,
        weight_tasks=scoring.W_TASKS,
        weight_code=scoring.W_CODE,
        weight_rhythm=scoring.W_RHYTHM,
        weight_reviews=scoring.W_REVIEWS,
        penalty_max=scoring.PENALTY_MAX,
        code_window_days=scoring.CODE_WINDOW_DAYS,
        rhythm_window_days=scoring.RHYTHM_WINDOW_DAYS,
        rhythm_target_days=scoring.RHYTHM_TARGET_DAYS,
        normalize_cap=scoring.NORMALIZE_CAP,
        max_lines_per_commit=scoring.MAX_LINES_PER_COMMIT,
        stuck_red_days=scoring.STUCK_RED_DAYS,
        yellow_streak_days=scoring.YELLOW_STREAK_DAYS,
        yellow_to_red_extra_days=scoring.YELLOW_TO_RED_EXTRA_DAYS,
        # 40% ниже медианы и 4 дня без активности — пороги из _member_at_risk_on_date.
        yellow_below_median_percent=40,
        yellow_inactive_days=4,
    )
