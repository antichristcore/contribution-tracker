import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.deps import get_current_member, get_db, require_teamlead
from backend.app.models import Member, ScoreHistory, StatusColor, SystemRole, Team
from backend.app.schemas import ScoreHistoryOut, TeamSummaryMemberOut, TeamSummaryOut
from backend.app.services.recalc import recalculate_team_scores
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
    members = (
        db.query(Member)
        .filter(
            Member.team_id == teamlead.team_id,
            Member.is_active.is_(True),
            Member.system_role != SystemRole.teamlead,
        )
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
