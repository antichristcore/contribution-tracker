from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models import Member, ScoreHistory, StatusColor, SystemRole, Team
from backend.app.services import notifications
from backend.app.services.scoring import compute_team_scores, evaluate_thresholds
from backend.app.utils.time import utcnow


async def recalculate_team_scores(db: Session, team: Team, as_of: datetime | None = None) -> list[dict]:
    as_of = as_of or utcnow()
    # The teamlead isn't a tracked contributor — the whole point of the product is
    # monitoring the *team*, and every member-facing screen already hides
    # them from the roster, so they shouldn't show up in score/status counts.
    members = (
        db.query(Member)
        .filter(Member.team_id == team.id, Member.is_active.is_(True), Member.system_role != SystemRole.teamlead)
        .all()
    )
    computed = compute_team_scores(db, members, as_of)

    rows: list[tuple[ScoreHistory, Member, dict]] = []
    for item in computed:
        raw = item["raw"]
        row = ScoreHistory(
            team_id=team.id,
            member_id=item["member"].id,
            computed_at=as_of,
            contribution_score=item["score"],
            commits_count_7d=raw["commits_count_7d"],
            commits_lines_changed_7d=raw["commits_lines_changed_7d"],
            tasks_assigned=raw["tasks_assigned"],
            tasks_completed_on_time=raw["tasks_completed_on_time"],
            tasks_status_stuck_days_max=raw["tasks_status_stuck_days_max"],
            pr_review_comments_given=raw["pr_review_comments_given"],
            last_activity_days_ago=raw["last_activity_days_ago"],
            status_color=StatusColor.no_data,
            has_data=raw["has_data"],
        )
        db.add(row)
        rows.append((row, item["member"], raw))
    db.commit()

    summary = []
    for row, member, raw in rows:
        status_color = (
            evaluate_thresholds(db, team.id, member.id, as_of) if raw["has_data"] else StatusColor.no_data
        )
        row.status_color = status_color
        db.commit()
        await notifications.process_member_threshold(db, team.id, member, status_color, raw, as_of)
        summary.append(
            {
                "member_id": member.id,
                "display_name": member.display_name,
                "score": row.contribution_score,
                "status_color": status_color.value,
            }
        )
    return summary
