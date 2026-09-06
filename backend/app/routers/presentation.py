import statistics
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.deps import get_db, require_teamlead
from backend.app.models import Member, NotificationLog, ScoreHistory, SystemRole
from backend.app.schemas import _round_score
from backend.app.utils.time import utcnow

router = APIRouter(prefix="/api/presentation", tags=["presentation"])


@router.get("/before-after")
def before_after(
    days: int = settings.SCORE_LOOKBACK_DAYS,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> dict:
    since = utcnow() - timedelta(days=days)
    members = (
        db.query(Member)
        .filter(
            Member.team_id == teamlead.team_id,
            Member.is_active.is_(True),
            Member.system_role != SystemRole.teamlead,
        )
        .all()
    )

    rows = (
        db.query(ScoreHistory)
        .filter(ScoreHistory.team_id == teamlead.team_id, ScoreHistory.computed_at >= since)
        .order_by(ScoreHistory.computed_at.asc())
        .all()
    )

    by_day: dict[str, list[ScoreHistory]] = {}
    for r in rows:
        key = r.computed_at.date().isoformat()
        by_day.setdefault(key, []).append(r)

    # Медиана — по тем же людям, чьи линии нарисованы на графике. Балл тимлида
    # тоже пишется в историю, но он не участник наблюдения: его линии здесь нет,
    # и в пульсе команды и в порогах его тоже нет — пунктир обязан считаться по
    # той же группе, иначе одна и та же «середина команды» на трёх экранах разная.
    tracked_ids = {m.id for m in members}
    days_sorted = sorted(by_day.keys())
    team_median_by_day = []
    for d in days_sorted:
        scores = [
            r.contribution_score
            for r in by_day[d]
            if r.member_id in tracked_ids and r.contribution_score is not None
        ]
        median = statistics.median(scores) if scores else None
        team_median_by_day.append({"date": d, "median": _round_score(median)})

    per_member = []
    for m in members:
        series = []
        for d in days_sorted:
            match = next((r for r in by_day[d] if r.member_id == m.id), None)
            series.append({"date": d, "score": _round_score(match.contribution_score) if match else None})
        per_member.append({"member_id": m.id, "display_name": m.display_name, "series": series})

    notifications = (
        db.query(NotificationLog)
        .join(Member, Member.id == NotificationLog.member_id)
        .filter(Member.team_id == teamlead.team_id, NotificationLog.sent_at >= since)
        .order_by(NotificationLog.sent_at.asc())
        .all()
    )

    return {
        "days": days_sorted,
        "team_median_by_day": team_median_by_day,
        "members": per_member,
        "notifications": [
            {
                "member_id": n.member_id,
                "type": n.type.value,
                "sent_at": n.sent_at.isoformat(),
                "payload_summary": n.payload_summary,
            }
            for n in notifications
        ],
    }
